"""Chat-completion adapters.

Three wire protocols cover practically every hosted and self-hosted model:

* ``openai`` — the OpenAI Chat Completions protocol, also spoken by Azure
  OpenAI, Ollama, vLLM, LM Studio, Groq, Together, Mistral, DeepSeek,
  OpenRouter, Fireworks and most gateways (set ``base_url``).
* ``anthropic`` — the Anthropic Messages API (Claude models).
* ``gemini`` — the Google Generative Language API.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from . import http
from .types import ChatMessage, ChatResult, ModelSpec, ProviderError, Usage

OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
ANTHROPIC_DEFAULT_BASE = "https://api.anthropic.com/v1"
GEMINI_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"
ANTHROPIC_VERSION = "2023-06-01"


class ChatClient(ABC):
    """One configured chat model."""

    protocol: str = ""

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    @property
    def label(self) -> str:
        return self.spec.label

    @abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 800,
        json_mode: bool = False,
        timeout: float = 30.0,
    ) -> ChatResult:
        """Generate one completion or raise ProviderError."""

    async def list_models(self, timeout: float = 15.0) -> list[str]:
        """Model ids the credentials can use (best effort)."""
        return []


def _base(spec: ModelSpec, default: str) -> str:
    """Explicit base_url, else the provider's own endpoint, else ``default``.

    Falling straight back to ``default`` sent e.g. a Groq key to OpenAI.
    """
    from .catalog import default_base_url

    base = spec.base_url or default_base_url(spec.provider) or default
    return base.rstrip("/")


class OpenAICompatibleChat(ChatClient):
    protocol = "openai"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.spec.api_key:
            if self.spec.option("azure"):
                headers["api-key"] = self.spec.api_key
            else:
                headers["Authorization"] = f"Bearer {self.spec.api_key}"
        return headers

    def _url(self, path: str) -> str:
        url = f"{_base(self.spec, OPENAI_DEFAULT_BASE)}{path}"
        api_version = self.spec.option("api_version")
        return f"{url}?api-version={api_version}" if api_version else url

    async def complete(self, messages, *, system=None, temperature=0.0, max_tokens=800,
                       json_mode=False, timeout=30.0) -> ChatResult:
        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend({"role": m.role, "content": m.content} for m in messages)
        payload: dict[str, Any] = {
            "model": self.spec.model,
            "messages": payload_messages,
            "temperature": temperature,
        }
        # Newer OpenAI reasoning models reject max_tokens; others ignore the newer name.
        token_param = self.spec.option("max_tokens_param", "max_tokens")
        payload[token_param] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = await http.post_json(
            self.label, self._url("/chat/completions"),
            json=payload, headers=self._headers(), timeout=timeout,
        )
        choices = data.get("choices") or []
        usage = data.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        result_usage = Usage(
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cached_tokens=int(details.get("cached_tokens") or 0),
        )
        if not choices:
            return ChatResult(None, self.spec.model, self.spec.provider, "blocked", result_usage)
        choice = choices[0]
        text = (choice.get("message") or {}).get("content")
        finish = choice.get("finish_reason") or "stop"
        if finish == "content_filter" or not text:
            return ChatResult(None, self.spec.model, self.spec.provider, "blocked", result_usage)
        return ChatResult(text, self.spec.model, self.spec.provider,
                          "length" if finish == "length" else "stop", result_usage)

    async def list_models(self, timeout: float = 15.0) -> list[str]:
        data = await http.get_json(self.label, self._url("/models"),
                                   headers=self._headers(), timeout=timeout)
        return sorted(str(item.get("id")) for item in data.get("data", []) if item.get("id"))


class AnthropicChat(ChatClient):
    protocol = "anthropic"

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.spec.api_key or "",
            "anthropic-version": ANTHROPIC_VERSION,
        }

    async def complete(self, messages, *, system=None, temperature=0.0, max_tokens=800,
                       json_mode=False, timeout=30.0) -> ChatResult:
        # The Messages API requires alternating turns that start with "user".
        turns: list[dict[str, str]] = []
        for message in messages:
            if message.role == "system":
                system = f"{system}\n\n{message.content}" if system else message.content
                continue
            if turns and turns[-1]["role"] == message.role:
                turns[-1]["content"] += f"\n\n{message.content}"
            else:
                turns.append({"role": message.role, "content": message.content})
        if not turns or turns[0]["role"] != "user":
            turns.insert(0, {"role": "user", "content": "(conversation start)"})
        if json_mode:
            system = (system or "") + "\n\nRespond with a single valid JSON object and nothing else."
        payload: dict[str, Any] = {
            "model": self.spec.model,
            "messages": turns,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        data = await http.post_json(
            self.label, f"{_base(self.spec, ANTHROPIC_DEFAULT_BASE)}/messages",
            json=payload, headers=self._headers(), timeout=timeout,
        )
        usage = data.get("usage") or {}
        result_usage = Usage(
            prompt_tokens=int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0),
            completion_tokens=int(usage.get("output_tokens") or 0),
            cached_tokens=int(usage.get("cache_read_input_tokens") or 0),
        )
        text = "".join(
            block.get("text", "") for block in data.get("content") or [] if block.get("type") == "text"
        )
        stop = data.get("stop_reason")
        if stop == "refusal" or not text:
            return ChatResult(None, self.spec.model, self.spec.provider, "blocked", result_usage)
        return ChatResult(text, self.spec.model, self.spec.provider,
                          "length" if stop == "max_tokens" else "stop", result_usage)

    async def list_models(self, timeout: float = 15.0) -> list[str]:
        data = await http.get_json(self.label, f"{_base(self.spec, ANTHROPIC_DEFAULT_BASE)}/models",
                                   headers=self._headers(), timeout=timeout)
        return sorted(str(item.get("id")) for item in data.get("data", []) if item.get("id"))


def gemini_model_id(model: str) -> str:
    return model.split("/", 1)[1] if model.startswith("models/") else model


class GeminiChat(ChatClient):
    protocol = "gemini"

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "x-goog-api-key": self.spec.api_key or ""}

    async def complete(self, messages, *, system=None, temperature=0.0, max_tokens=800,
                       json_mode=False, timeout=30.0) -> ChatResult:
        contents = []
        for message in messages:
            if message.role == "system":
                system = f"{system}\n\n{message.content}" if system else message.content
                continue
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})
        config: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if json_mode:
            config["responseMimeType"] = "application/json"
        payload: dict[str, Any] = {"contents": contents, "generationConfig": config}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = (f"{_base(self.spec, GEMINI_DEFAULT_BASE)}/models/"
               f"{gemini_model_id(self.spec.model)}:generateContent")
        data = await http.post_json(self.label, url, json=payload,
                                    headers=self._headers(), timeout=timeout)
        meta = data.get("usageMetadata") or {}
        result_usage = Usage(
            prompt_tokens=int(meta.get("promptTokenCount") or 0),
            completion_tokens=int(meta.get("candidatesTokenCount") or 0),
            cached_tokens=int(meta.get("cachedContentTokenCount") or 0),
        )
        candidates = data.get("candidates") or []
        if not candidates:
            return ChatResult(None, self.spec.model, self.spec.provider, "blocked", result_usage)
        candidate = candidates[0]
        text = "".join(
            part.get("text", "") for part in (candidate.get("content") or {}).get("parts") or []
            if not part.get("thought")
        )
        finish = candidate.get("finishReason") or "STOP"
        if finish in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"} or not text:
            return ChatResult(None, self.spec.model, self.spec.provider, "blocked", result_usage)
        return ChatResult(text, self.spec.model, self.spec.provider,
                          "length" if finish == "MAX_TOKENS" else "stop", result_usage)

    async def list_models(self, timeout: float = 15.0) -> list[str]:
        data = await http.get_json(self.label, f"{_base(self.spec, GEMINI_DEFAULT_BASE)}/models",
                                   headers=self._headers(), timeout=timeout)
        return sorted(
            gemini_model_id(str(item["name"])) for item in data.get("models", [])
            if "generateContent" in (item.get("supportedGenerationMethods") or [])
        )


_CHAT_ADAPTERS: dict[str, type[ChatClient]] = {
    "openai": OpenAICompatibleChat,
    "anthropic": AnthropicChat,
    "gemini": GeminiChat,
}


def build_chat_client(spec: ModelSpec) -> ChatClient:
    from .catalog import protocol_for

    protocol = protocol_for(spec.provider, capability="chat")
    adapter = _CHAT_ADAPTERS.get(protocol)
    if adapter is None:
        raise ProviderError(f"Unsupported chat provider: {spec.provider}", provider=spec.provider)
    return adapter(spec)
