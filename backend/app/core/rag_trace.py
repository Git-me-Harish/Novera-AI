"""Request-scoped, privacy-preserving RAG trace context.

This is intentionally dependency-light. It emits structured Loguru records now
and provides a stable event shape for OpenTelemetry/exporters later. Raw HR,
Finance queries and document text are never stored in the trace.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from loguru import logger

_CURRENT_TRACE: ContextVar["RAGTrace | None"] = ContextVar("current_rag_trace", default=None)


def hash_value(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class RAGTrace:
    request_id: str
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str | None = None
    user_id: str | None = None
    query_hash: str | None = None
    started_at: float = field(default_factory=time.perf_counter)
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    status_code: int | None = None
    error: str | None = None

    def set_principal(self, *, tenant_id: Any = None, user_id: Any = None) -> None:
        self.tenant_id = str(tenant_id) if tenant_id is not None else self.tenant_id
        self.user_id = str(user_id) if user_id is not None else self.user_id

    def set_query(self, query: str) -> None:
        self.query_hash = hash_value(query)

    def stage_start(self, name: str) -> float:
        return time.perf_counter()

    def stage_end(self, name: str, started: float, **fields: Any) -> None:
        stage = self.stages.setdefault(name, {})
        stage["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        stage.update(_safe_fields(fields))

    def event(self, name: str, **fields: Any) -> None:
        self.events.append({"name": name, **_safe_fields(fields)})

    def finish(self, status_code: int | None = None, error: BaseException | None = None) -> None:
        self.status_code = status_code
        if error is not None:
            self.error = type(error).__name__
        payload = self.to_dict()
        logger.info("RAG_TRACE {}", json.dumps(payload, separators=(",", ":"), sort_keys=True))

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "query_hash": self.query_hash,
            "latency_ms": round((time.perf_counter() - self.started_at) * 1000, 3),
            "stages": self.stages,
            "events": self.events,
            "status_code": self.status_code,
            "error": self.error,
        }


def _safe_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Allow metrics/identifiers; prevent accidental content/query logging."""
    allowed = {
        "strategy", "candidate_k", "final_k", "retrieved", "reranked", "sources",
        "context_tokens", "prompt_tokens", "completion_tokens", "total_tokens",
        "cache_hit", "model", "embedding_model", "embedding_dimensions", "citation_count",
        "finish_reason", "abstained", "valid", "error_type", "status", "expanded_to_global",
        "min_score", "max_score", "avg_score",
    }
    result = {}
    for key, value in fields.items():
        if key not in allowed:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = value
        elif isinstance(value, (list, tuple)) and all(isinstance(item, (str, int, float, bool)) for item in value):
            result[key] = list(value)
    return result


def get_current_trace() -> RAGTrace | None:
    return _CURRENT_TRACE.get()


@contextmanager
def trace_context(trace: RAGTrace) -> Iterator[RAGTrace]:
    token = _CURRENT_TRACE.set(trace)
    try:
        yield trace
    finally:
        _CURRENT_TRACE.reset(token)


__all__ = ["RAGTrace", "get_current_trace", "hash_value", "trace_context"]
