"""Provider-neutral types for chat, embedding and rerank models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
        }


@dataclass
class ChatResult:
    """A completed generation.

    ``text`` is None when the provider returned no usable candidate (safety
    block, empty choice). That is deterministic and must not be retried.
    """

    text: Optional[str]
    model: str
    provider: str
    finish_reason: str = "stop"
    usage: Usage = field(default_factory=Usage)
    cache_hit: bool = False


@dataclass(frozen=True)
class ModelSpec:
    """Everything needed to reach one model. Never log ``api_key``."""

    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extra: tuple[tuple[str, Any], ...] = ()

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    def option(self, key: str, default: Any = None) -> Any:
        return dict(self.extra).get(key, default)

    def __repr__(self) -> str:  # keep keys out of logs and tracebacks
        return f"ModelSpec(provider={self.provider!r}, model={self.model!r}, base_url={self.base_url!r})"


class ProviderError(Exception):
    """A provider call failed.

    ``retryable`` marks transient conditions (rate limit, 5xx, timeout).
    ``billing`` marks exhausted credits or quota that waiting cannot fix.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status: Optional[int] = None,
        retryable: bool = False,
        billing: bool = False,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.retryable = retryable
        self.billing = billing
        self.retry_after = retry_after


class ProviderNotConfigured(ProviderError):
    """No model or credentials are configured for this capability."""

    def __init__(self, message: str, provider: str = "none") -> None:
        super().__init__(message, provider=provider)
