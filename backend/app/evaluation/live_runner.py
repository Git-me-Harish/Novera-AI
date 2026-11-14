"""Record production-pipeline predictions for a golden-set evaluation run.

This module deliberately keeps raw retrieved content in memory only. It is
written to the prediction artifact only when ``include_content`` is explicitly
enabled for a protected evaluation environment.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.evaluation.metrics import evidence_matches
from app.evaluation.runner import load_jsonl
from app.evaluation.schemas import GoldenExample
from app.services.embedding.embedding_service import embedding_service
from app.services.ai.pricing import estimate_cost
from app.services.generation.chat_service import chat_service
from app.services.generation.conversation_manager import InMemoryConversationStore

_ABSTENTION_REASONS = {"insufficient_context", "output_guardrail_rejected", "blocked"}
_FAILURE_REASONS = {"provider_unavailable", "error"}


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _safe_retrieved_chunk(
    chunk: dict[str, Any], include_content: bool, example: GoldenExample | None = None
) -> dict[str, Any]:
    content = str(chunk.get("content", "") or "")
    result = {
        "chunk_id": str(chunk.get("chunk_id") or chunk.get("id") or ""),
        "document_id": str(chunk.get("document_id") or ""),
        "document_name": str(chunk.get("document_name") or ""),
        "score": chunk.get("rerank_score", chunk.get("fused_score", chunk.get("similarity_score"))),
        "retrieval_method": chunk.get("retrieval_method", []),
        "content_sha256": _content_hash(content),
    }
    if example is not None and example.evidence:
        # Matched here, while the text is in memory, so artifacts can stay
        # content-free and labels survive re-chunking.
        result["evidence_matches"] = evidence_matches(
            example,
            document_id=result["document_id"],
            document_name=result["document_name"],
            content=content,
        )
    if include_content:
        result["content"] = content
    return result


async def _pre_rerank_items(db, example: GoldenExample, chunk_ids: list[str]) -> list[dict[str, Any]]:
    """Pre-rerank candidates in order, evidence-matched like the final list."""
    items: list[dict[str, Any]] = [{"chunk_id": chunk_id} for chunk_id in chunk_ids]
    if not example.evidence or not chunk_ids:
        return items
    from sqlalchemy import select

    from app.models.document import Chunk, Document

    rows = (await db.execute(
        select(Chunk.id, Chunk.document_id, Chunk.content, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.id.in_([UUID(c) for c in chunk_ids]))
    )).all()
    by_id = {str(row.id): row for row in rows}
    for item in items:
        row = by_id.get(item["chunk_id"])
        if row is not None:
            item["evidence_matches"] = evidence_matches(
                example, document_id=str(row.document_id), document_name=row.filename, content=row.content
            )
    return items


async def collect_retrieval(examples: list[GoldenExample]) -> list[dict[str, Any]]:
    """Retrieval-only run: the production retrieval pipeline, no generation.

    Measures recall/MRR/nDCG and reranker lift without calling the answering
    model (useful when it is unavailable, and cheaper while tuning retrieval).
    """
    from app.services.retrieval.pipeline import retrieval_pipeline

    predictions = []
    for example in examples:
        started = time.perf_counter()
        prediction: dict[str, Any] = {"id": example.id, "retrieved": [], "answer": "", "mode": "retrieval_only"}
        try:
            async with AsyncSessionLocal() as db:
                result = await retrieval_pipeline.retrieve(
                    query=example.question, db=db, organization_id=UUID(example.tenant)
                )
                metadata = result.get("retrieval_metadata", {}) or {}
                prediction["retrieved"] = [
                    _safe_retrieved_chunk(chunk, False, example) for chunk in result.get("chunks", [])
                ]
                prediction["pre_rerank_retrieved"] = await _pre_rerank_items(
                    db, example, metadata.get("pre_rerank_chunk_ids", [])
                )
                prediction["retrieval_metadata"] = metadata
                await db.rollback()
        except Exception as exc:
            prediction["error"] = type(exc).__name__
        finally:
            prediction["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            predictions.append(prediction)
    return predictions


async def collect_predictions(
    examples: list[GoldenExample],
    *,
    include_content: bool = False,
) -> list[dict[str, Any]]:
    """Run every golden example through the production chat path once."""
    predictions = []
    for example in examples:
        started = time.perf_counter()
        prediction: dict[str, Any] = {
            "id": example.id,
            "retrieved": [],
            "answer": "",
            "abstained": False,
            "latency_ms": 0.0,
            "retrieval_metadata": {},
            "configuration": {
                "embedding_provider": embedding_service.provider,
                "embedding_model": embedding_service.model_name,
                "embedding_dimensions": embedding_service.dimensions,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "retrieval_top_k": settings.retrieval_top_k,
                "global_search_top_k": settings.global_search_top_k,
                "rerank_top_k": settings.rerank_top_k,
                "min_rerank_score": settings.min_rerank_score,
                "focused_context_chunks": settings.focused_context_chunks,
                "complex_context_chunks": settings.complex_context_chunks,
                "rerank_model": f"{settings.rerank_provider}:{settings.rerank_model}",
                "generation_model": f"{settings.llm_provider}:{settings.llm_model}",
                "llm_max_concurrency": settings.llm_max_concurrency,
                "llm_answer_timeout_seconds": settings.llm_answer_timeout_seconds,
                "llm_attempt_timeout_seconds": settings.llm_attempt_timeout_seconds,
            },
        }
        try:
            organization_id = UUID(example.tenant)
            async with AsyncSessionLocal() as db:
                # Drive the exact request path users hit: input guardrails,
                # classification, reformulation, retrieval, generation and the
                # output policy. Each question gets a fresh conversation, and
                # the semantic cache is bypassed so runs measure cold quality.
                result = await chat_service.chat(
                    query=example.question,
                    conversation_id=None,
                    user_id=f"evaluation:{example.id}",
                    organization_id=organization_id,
                    db=db,
                    stream=False,
                    use_semantic_cache=False,
                    return_evidence=True,
                    # Real chat path, but nothing written to the tenant's history.
                    store=InMemoryConversationStore(),
                )
                await db.rollback()
            evidence = result.get("evidence", {})
            metadata = result.get("metadata", {})
            retrieval_metadata = metadata.get("retrieval_metadata", {}) or {}
            prediction["retrieved"] = [
                _safe_retrieved_chunk(chunk, include_content, example)
                for chunk in evidence.get("chunks", [])
            ]
            prediction["sources"] = result.get("sources", [])
            prediction["source_count"] = len(prediction["sources"])
            prediction["retrieval_metadata"] = retrieval_metadata
            async with AsyncSessionLocal() as db:
                prediction["pre_rerank_retrieved"] = await _pre_rerank_items(
                    db, example, retrieval_metadata.get("pre_rerank_chunk_ids", [])
                )
            prediction["retrieval_latency_ms"] = evidence.get("retrieval_latency_ms", 0.0)
            prediction["generation_latency_ms"] = evidence.get("generation_latency_ms", 0.0)
            prediction["answer"] = result.get("answer", "")
            prediction["validation"] = evidence.get("validation", {})
            prediction["searched_documents"] = evidence.get("should_search")
            finish_reason = evidence.get("finish_reason")
            prediction["finish_reason"] = finish_reason
            usage = metadata.get("tokens", {}) or {}
            prediction["prompt_tokens"] = int(usage.get("prompt_tokens", 0) or 0)
            prediction["completion_tokens"] = int(usage.get("completion_tokens", 0) or 0)
            prediction["generation_model"] = metadata.get("model")
            prediction["estimated_cost_usd"] = estimate_cost(metadata.get("model"), usage) or 0.0
            prediction["cache_hit"] = bool(metadata.get("cache_hit", False))
            if finish_reason in _ABSTENTION_REASONS:
                prediction["abstained"] = True
            elif finish_reason in _FAILURE_REASONS or result.get("status") == "rejected":
                # An outage or a rejected input is a system failure, not a
                # wrong answer and not an abstention.
                prediction["error"] = f"finish_reason={finish_reason or result.get('status')}"
        except Exception as exc:
            prediction["error"] = type(exc).__name__
            prediction["abstained"] = False
        finally:
            prediction["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            predictions.append(prediction)
    return predictions


async def _cli_async(args: argparse.Namespace) -> int:
    examples = load_jsonl(args.dataset, GoldenExample)
    if args.retrieval_only:
        predictions = await collect_retrieval(examples)
    else:
        predictions = await collect_predictions(
            examples,
            include_content=args.include_content,
        )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction, ensure_ascii=False) + "\n")
    print(f"Recorded {len(predictions)} predictions to {output}")
    return 0 if not any(p.get("error") for p in predictions) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Record predictions from the production Novera RAG pipeline")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--include-content",
        action="store_true",
        help="Include retrieved text in the protected artifact for faithfulness evaluation",
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Run retrieval without generation (no answering-model calls)",
    )
    return asyncio.run(_cli_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
