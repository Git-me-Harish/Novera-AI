"""Rerank adapter for the Cohere-style /rerank protocol.

Cohere (v2), Jina, Voyage, Hugging Face TEI and most self-hosted rerankers
accept {model, query, documents, top_n} and return indices with relevance
scores, under either ``results`` or ``data``.
"""
from __future__ import annotations

from . import http
from .types import ModelSpec


class RerankClient:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    @property
    def label(self) -> str:
        return self.spec.label

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int, timeout: float = 10.0
    ) -> list[tuple[int, float]]:
        """Return (document index, relevance score) pairs, best first."""
        from .catalog import default_base_url

        base = (self.spec.base_url or default_base_url(self.spec.provider, "rerank") or "").rstrip("/")
        headers = {"Content-Type": "application/json"}
        if self.spec.api_key:
            headers["Authorization"] = f"Bearer {self.spec.api_key}"
        payload = {
            "model": self.spec.model,
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
        }
        # Voyage names the limit top_k.
        if self.spec.option("top_k_param"):
            payload[self.spec.option("top_k_param")] = payload.pop("top_n")
        data = await http.post_json(self.label, f"{base}/rerank", json=payload,
                                    headers=headers, timeout=timeout)
        rows = data.get("results") or data.get("data") or []
        pairs = [(int(row["index"]), float(row["relevance_score"])) for row in rows]
        return sorted(pairs, key=lambda pair: pair[1], reverse=True)[:top_n]
