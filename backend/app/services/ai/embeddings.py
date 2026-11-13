"""Embedding adapters (OpenAI-compatible and Gemini)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from . import http
from .chat import GEMINI_DEFAULT_BASE, OPENAI_DEFAULT_BASE, gemini_model_id
from .types import ModelSpec, ProviderError

Task = Literal["query", "document"]


class EmbeddingClient(ABC):
    def __init__(self, spec: ModelSpec, dimensions: int, batch_size: int = 64) -> None:
        self.spec = spec
        self.dimensions = dimensions
        self.batch_size = batch_size

    @property
    def label(self) -> str:
        return self.spec.label

    async def embed(self, texts: list[str], *, task: Task, timeout: float = 60.0) -> list[list[float]]:
        """Embed texts in batches; always returns exactly one vector per input."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            result = await self._embed_batch(batch, task=task, timeout=timeout)
            if len(result) != len(batch):
                raise ProviderError(
                    f"{self.label} returned {len(result)} vectors for {len(batch)} inputs",
                    provider=self.spec.provider,
                )
            vectors.extend(result)
        for vector in vectors:
            if len(vector) != self.dimensions:
                # Never pad or truncate: a different size means a different
                # vector space, and mixing spaces silently corrupts retrieval.
                raise ProviderError(
                    f"{self.label} returned {len(vector)}-d vectors; the index requires "
                    f"{self.dimensions}-d. Reconfigure EMBEDDING_DIMENSIONS and re-embed.",
                    provider=self.spec.provider,
                )
        return vectors

    @abstractmethod
    async def _embed_batch(self, texts: list[str], *, task: Task, timeout: float) -> list[list[float]]:
        ...


class OpenAICompatibleEmbeddings(EmbeddingClient):
    async def _embed_batch(self, texts, *, task, timeout):
        headers = {"Content-Type": "application/json"}
        if self.spec.api_key:
            headers["Authorization"] = f"Bearer {self.spec.api_key}"
        payload: dict[str, Any] = {"model": self.spec.model, "input": texts}
        if self.spec.option("send_dimensions", True):
            payload["dimensions"] = self.dimensions
        # Asymmetric models (Voyage, Jina, Cohere) take a query/document hint.
        input_type_param = self.spec.option("input_type_param")
        if input_type_param:
            payload[input_type_param] = self.spec.option(f"{task}_input_type", task)
        from .catalog import default_base_url

        base = (self.spec.base_url or default_base_url(self.spec.provider, "embedding")
                or OPENAI_DEFAULT_BASE).rstrip("/")
        data = await http.post_json(self.label, f"{base}/embeddings", json=payload,
                                    headers=headers, timeout=timeout)
        rows = sorted(data.get("data") or [], key=lambda row: row.get("index", 0))
        return [[float(v) for v in row["embedding"]] for row in rows]


class GeminiEmbeddings(EmbeddingClient):
    _TASKS = {"query": "RETRIEVAL_QUERY", "document": "RETRIEVAL_DOCUMENT"}

    async def _embed_batch(self, texts, *, task, timeout):
        model_id = gemini_model_id(self.spec.model)
        base = (self.spec.base_url or GEMINI_DEFAULT_BASE).rstrip("/")
        payload = {
            "requests": [
                {
                    "model": f"models/{model_id}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": self._TASKS[task],
                    "outputDimensionality": self.dimensions,
                }
                for text in texts
            ]
        }
        data = await http.post_json(
            self.label, f"{base}/models/{model_id}:batchEmbedContents", json=payload,
            headers={"Content-Type": "application/json", "x-goog-api-key": self.spec.api_key or ""},
            timeout=timeout,
        )
        return [[float(v) for v in row["values"]] for row in data.get("embeddings") or []]


def build_embedding_client(spec: ModelSpec, dimensions: int, batch_size: int = 64) -> EmbeddingClient:
    from .catalog import protocol_for

    protocol = protocol_for(spec.provider, capability="embedding")
    if protocol == "gemini":
        return GeminiEmbeddings(spec, dimensions, min(batch_size, 100))
    return OpenAICompatibleEmbeddings(spec, dimensions, batch_size)
