"""Known providers: wire protocol, default endpoint and capabilities.

This catalog deliberately contains no model names. Models are always chosen
by configuration (platform defaults) or by a tenant admin, and can be
discovered live through each provider's model-listing endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass

from .types import ProviderError


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    chat_protocol: str | None
    embedding_protocol: str | None
    rerank_protocol: str | None
    default_base_url: str | None
    requires_api_key: bool = True
    requires_base_url: bool = False
    note: str = ""


PROVIDERS: dict[str, ProviderInfo] = {p.id: p for p in [
    ProviderInfo("openai", "OpenAI", "openai", "openai", None, "https://api.openai.com/v1"),
    ProviderInfo("azure_openai", "Azure OpenAI", "openai", "openai", None, None,
                 requires_base_url=True,
                 note="base_url = https://<resource>.openai.azure.com/openai/deployments/<deployment>"),
    ProviderInfo("anthropic", "Anthropic (Claude)", "anthropic", None, None,
                 "https://api.anthropic.com/v1"),
    ProviderInfo("gemini", "Google Gemini", "gemini", "gemini", None,
                 "https://generativelanguage.googleapis.com/v1beta"),
    ProviderInfo("mistral", "Mistral", "openai", "openai", None, "https://api.mistral.ai/v1"),
    ProviderInfo("groq", "Groq", "openai", None, None, "https://api.groq.com/openai/v1"),
    ProviderInfo("together", "Together AI", "openai", "openai", None, "https://api.together.xyz/v1"),
    ProviderInfo("deepseek", "DeepSeek", "openai", None, None, "https://api.deepseek.com/v1"),
    ProviderInfo("xai", "xAI", "openai", None, None, "https://api.x.ai/v1"),
    ProviderInfo("openrouter", "OpenRouter", "openai", None, None, "https://openrouter.ai/api/v1"),
    ProviderInfo("fireworks", "Fireworks AI", "openai", "openai", None,
                 "https://api.fireworks.ai/inference/v1"),
    ProviderInfo("cohere", "Cohere", "openai", "openai", "cohere",
                 "https://api.cohere.ai/compatibility/v1",
                 note="Rerank uses https://api.cohere.com/v2"),
    ProviderInfo("jina", "Jina AI", None, "openai", "cohere", "https://api.jina.ai/v1"),
    ProviderInfo("voyage", "Voyage AI", None, "openai", "cohere", "https://api.voyageai.com/v1"),
    ProviderInfo("ollama", "Ollama (self-hosted)", "openai", "openai", None,
                 "http://localhost:11434/v1", requires_api_key=False),
    ProviderInfo("vllm", "vLLM (self-hosted)", "openai", "openai", None, None,
                 requires_api_key=False, requires_base_url=True),
    ProviderInfo("lmstudio", "LM Studio (self-hosted)", "openai", "openai", None,
                 "http://localhost:1234/v1", requires_api_key=False),
    ProviderInfo("openai_compatible", "Other OpenAI-compatible endpoint", "openai", "openai",
                 "cohere", None, requires_api_key=False, requires_base_url=True),
]}

# Historical names stored on existing chunks/settings.
ALIASES = {"google": "gemini", "azure": "azure_openai"}


def provider_info(provider: str) -> ProviderInfo:
    key = ALIASES.get(provider, provider)
    info = PROVIDERS.get(key)
    if info is None:
        raise ProviderError(f"Unknown provider: {provider}", provider=provider)
    return info


def protocol_for(provider: str, *, capability: str) -> str:
    info = provider_info(provider)
    protocol = {
        "chat": info.chat_protocol,
        "embedding": info.embedding_protocol,
        "rerank": info.rerank_protocol,
    }[capability]
    if protocol is None:
        raise ProviderError(f"{info.label} does not support {capability}", provider=provider)
    return protocol


def default_base_url(provider: str, capability: str = "chat") -> str | None:
    info = provider_info(provider)
    if capability == "rerank" and info.id == "cohere":
        return "https://api.cohere.com/v2"
    return info.default_base_url


def catalog() -> list[dict]:
    return [
        {
            "id": info.id,
            "label": info.label,
            "capabilities": [
                name for name, proto in (
                    ("chat", info.chat_protocol),
                    ("embedding", info.embedding_protocol),
                    ("rerank", info.rerank_protocol),
                ) if proto
            ],
            "default_base_url": info.default_base_url,
            "requires_api_key": info.requires_api_key,
            "requires_base_url": info.requires_base_url,
            "note": info.note,
        }
        for info in PROVIDERS.values()
    ]
