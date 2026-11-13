"""Resolve which models serve a request: tenant override, platform default, fallbacks.

Chat models can be overridden per organization (including the tenant's own
API key, encrypted at rest). Embeddings stay platform-wide because every
stored vector must live in the same space as the query vectors; changing them
is a re-embedding operation, not a setting.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any, Optional
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

from .catalog import provider_info
from .chat import ChatClient, build_chat_client
from .embeddings import EmbeddingClient, build_embedding_client
from .rerank import RerankClient
from .types import ModelSpec, ProviderNotConfigured


# ── secrets ──────────────────────────────────────────────────────────────────

def _fernet() -> Fernet:
    material = settings.ai_secrets_key or settings.secret_key
    key = base64.urlsafe_b64encode(hashlib.sha256(f"novera-ai:{material}".encode()).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        # Rotated key or tampered value: treat as missing, never crash a request.
        logger.error("Stored tenant API key could not be decrypted; re-enter it in AI settings")
        return None


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return f"••••{value[-4:]}" if len(value) > 8 else "••••"


# ── tenant settings schema ───────────────────────────────────────────────────

class TenantChatModel(BaseModel):
    provider: str
    model: str = Field(min_length=1, max_length=200)
    base_url: Optional[str] = Field(default=None, max_length=500)
    api_key_encrypted: Optional[str] = None
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider")
    @classmethod
    def known_chat_provider(cls, value: str) -> str:
        info = provider_info(value)
        if not info.chat_protocol:
            raise ValueError(f"{info.label} does not provide chat models")
        return info.id


class TenantAISettings(BaseModel):
    """Stored under organizations.settings["ai"]."""

    chat: Optional[TenantChatModel] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_response_tokens: Optional[int] = Field(default=None, ge=64, le=16_000)
    # When the tenant's own model fails, may the platform model answer?
    allow_platform_fallback: bool = True


# ── platform specs ───────────────────────────────────────────────────────────

def _options(raw: str) -> tuple[tuple[str, Any], ...]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        logger.error("Ignoring invalid JSON in AI model options")
        return ()
    return tuple(sorted(parsed.items())) if isinstance(parsed, dict) else ()


def platform_chat_spec() -> Optional[ModelSpec]:
    if not (settings.llm_provider and settings.llm_model):
        return None
    return ModelSpec(settings.llm_provider, settings.llm_model,
                     settings.llm_api_key, settings.llm_base_url)


def platform_fallback_specs() -> list[ModelSpec]:
    specs = []
    for entry in filter(None, (e.strip() for e in settings.llm_fallback_models.split(","))):
        provider, _, model = entry.partition(":")
        if not model:
            logger.error(f"Ignoring LLM_FALLBACK_MODELS entry without 'provider:model': {entry}")
            continue
        same = provider == settings.llm_provider
        specs.append(ModelSpec(
            provider, model,
            settings.llm_api_key if same else settings.credential_for(provider),
            settings.llm_base_url if same else None,
        ))
    return specs


def platform_embedding_spec() -> Optional[ModelSpec]:
    if not (settings.embedding_provider and settings.embedding_model):
        return None
    return ModelSpec(settings.embedding_provider, settings.embedding_model,
                     settings.embedding_api_key, settings.embedding_base_url,
                     _options(settings.embedding_options))


def platform_rerank_spec() -> Optional[ModelSpec]:
    if not settings.rerank_provider or settings.rerank_provider == "none" or not settings.rerank_model:
        return None
    return ModelSpec(settings.rerank_provider, settings.rerank_model,
                     settings.rerank_api_key, settings.rerank_base_url)


def embedding_storage_identity(spec: ModelSpec) -> tuple[str, str]:
    """(provider, model) as stamped on stored chunks.

    Gemini vectors were historically stamped ("google", "models/<id>"); keep
    that exact identity so existing vectors remain searchable.
    """
    if provider_info(spec.provider).id == "gemini":
        model = spec.model if spec.model.startswith("models/") else f"models/{spec.model}"
        return "google", model
    return provider_info(spec.provider).id, spec.model


# ── resolution ───────────────────────────────────────────────────────────────

class ChatChain:
    """Ordered chat clients plus the generation parameters to use with them."""

    def __init__(self, clients: list[ChatClient], temperature: float, max_tokens: int,
                 source: str) -> None:
        self.clients = clients
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.source = source  # "tenant" or "platform", for traces

    @property
    def primary(self) -> ChatClient:
        return self.clients[0]

    @property
    def labels(self) -> list[str]:
        return [client.label for client in self.clients]


_TENANT_CACHE_SECONDS = 60.0
_tenant_cache: dict[str, tuple[float, Optional[TenantAISettings]]] = {}


def invalidate_tenant(organization_id: UUID | str) -> None:
    _tenant_cache.pop(str(organization_id), None)


async def load_tenant_settings(db, organization_id: UUID | str | None) -> Optional[TenantAISettings]:
    if organization_id is None or db is None:
        return None
    key = str(organization_id)
    cached = _tenant_cache.get(key)
    if cached and time.monotonic() - cached[0] < _TENANT_CACHE_SECONDS:
        return cached[1]
    from sqlalchemy import select

    from app.models.organization import Organization

    raw = (await db.execute(
        select(Organization.settings).where(Organization.id == organization_id)
    )).scalar_one_or_none() or {}
    tenant = None
    if raw.get("ai"):
        try:
            tenant = TenantAISettings.model_validate(raw["ai"])
        except Exception as exc:
            logger.error(f"Ignoring invalid AI settings for organization: {type(exc).__name__}")
    _tenant_cache[key] = (time.monotonic(), tenant)
    return tenant


def _platform_clients() -> list[ChatClient]:
    specs = [spec for spec in [platform_chat_spec(), *platform_fallback_specs()] if spec]
    return [build_chat_client(spec) for spec in specs]


def build_chain(tenant: Optional[TenantAISettings]) -> ChatChain:
    clients: list[ChatClient] = []
    source = "platform"
    if tenant and tenant.chat:
        chat = tenant.chat
        api_key = decrypt_secret(chat.api_key_encrypted) or settings.credential_for(chat.provider)
        clients.append(build_chat_client(ModelSpec(
            chat.provider, chat.model, api_key, chat.base_url, tuple(sorted(chat.options.items()))
        )))
        source = "tenant"
    if not clients or (tenant and tenant.allow_platform_fallback):
        clients.extend(c for c in _platform_clients() if c.label not in {x.label for x in clients})
    if not clients:
        raise ProviderNotConfigured(
            "No chat model configured. Set LLM_PROVIDER and LLM_MODEL, or configure "
            "a model in the organization's AI settings."
        )
    return ChatChain(
        clients,
        temperature=tenant.temperature if tenant and tenant.temperature is not None
        else settings.temperature,
        max_tokens=tenant.max_response_tokens if tenant and tenant.max_response_tokens
        else settings.max_response_tokens,
        source=source,
    )


async def chat_chain_for(db=None, organization_id: UUID | str | None = None) -> ChatChain:
    return build_chain(await load_tenant_settings(db, organization_id))


def platform_chain() -> ChatChain:
    return build_chain(None)


def utility_chain() -> ChatChain:
    """Cheaper model for titles and suggestions; falls back to the main chain."""
    if settings.llm_utility_model and settings.llm_provider:
        spec = ModelSpec(settings.llm_provider, settings.llm_utility_model,
                         settings.llm_api_key, settings.llm_base_url)
        chain = platform_chain()
        return ChatChain([build_chat_client(spec), *chain.clients], chain.temperature,
                         chain.max_tokens, "platform")
    return platform_chain()


_embedding_client: Optional[EmbeddingClient] = None
_rerank_client: Optional[RerankClient] = None
_rerank_resolved = False


def embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        spec = platform_embedding_spec()
        if spec is None:
            raise ProviderNotConfigured(
                "No embedding model configured. Set EMBEDDING_PROVIDER and EMBEDDING_MODEL."
            )
        _embedding_client = build_embedding_client(
            spec, settings.embedding_dimensions, settings.embedding_batch_size
        )
    return _embedding_client


def rerank_client() -> Optional[RerankClient]:
    global _rerank_client, _rerank_resolved
    if not _rerank_resolved:
        spec = platform_rerank_spec()
        _rerank_client = RerankClient(spec) if spec else None
        _rerank_resolved = True
    return _rerank_client


def reset_clients() -> None:
    """For tests and config reloads."""
    global _embedding_client, _rerank_client, _rerank_resolved
    _embedding_client = None
    _rerank_client = None
    _rerank_resolved = False
    _tenant_cache.clear()
