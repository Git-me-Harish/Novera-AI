"""Per-organization AI model settings (bring your own model and key).

Org admins choose the chat model for their organization from any supported
provider. API keys are encrypted at rest and never returned. Embeddings and
reranking stay platform-wide (see app.services.ai.registry for why).
"""
from __future__ import annotations

import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_org_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User
from app.services.ai import registry
from app.services.ai.catalog import catalog, default_base_url, provider_info
from app.services.ai.chat import build_chat_client
from app.services.ai.endpoint_policy import EndpointNotAllowed, validate_tenant_endpoint
from app.services.ai.types import ChatMessage, ModelSpec, ProviderError
from app.services.tenancy import audit
from app.services.tenancy.audit import Action

router = APIRouter()


class ChatModelInput(BaseModel):
    provider: str
    model: str = Field(min_length=1, max_length=200)
    base_url: Optional[str] = Field(default=None, max_length=500)
    # None keeps the stored key, "" removes it, any other value replaces it.
    api_key: Optional[str] = Field(default=None, max_length=500)


class AISettingsInput(BaseModel):
    chat: Optional[ChatModelInput] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_response_tokens: Optional[int] = Field(default=None, ge=64, le=16_000)
    allow_platform_fallback: bool = True


class ProbeInput(BaseModel):
    provider: str
    model: Optional[str] = Field(default=None, max_length=200)
    base_url: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=500)


async def _target_org(
    user: User, organization_id: Optional[UUID], db: AsyncSession
) -> Organization:
    """Org admins act on their own org; super admins must name one."""
    if user.is_super_admin():
        org_id = organization_id or user.organization_id
    else:
        if organization_id and organization_id != user.organization_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot manage another organization")
        org_id = user.organization_id
    if not org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "organization_id is required")
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return org


async def _effective_endpoint(provider: str, base_url: Optional[str]) -> Optional[str]:
    """Validate the URL this server will actually call for a tenant model."""
    info = provider_info(provider)
    effective = base_url or default_base_url(info.id)
    if info.requires_base_url and not base_url:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{info.label} requires a base URL")
    if effective is None:
        return None
    try:
        await validate_tenant_endpoint(effective)
    except EndpointNotAllowed as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Endpoint not allowed: {exc}")
    return base_url.rstrip("/") if base_url else None


def _stored(org: Organization) -> Optional[registry.TenantAISettings]:
    raw = (org.settings or {}).get("ai")
    return registry.TenantAISettings.model_validate(raw) if raw else None


def _public_view(org: Organization) -> dict:
    tenant = _stored(org)
    chain = registry.build_chain(tenant) if (tenant or registry.platform_chat_spec()) else None
    chat = None
    if tenant and tenant.chat:
        key = registry.decrypt_secret(tenant.chat.api_key_encrypted)
        chat = {
            "provider": tenant.chat.provider,
            "model": tenant.chat.model,
            "base_url": tenant.chat.base_url,
            "api_key_set": bool(key),
            "api_key_hint": registry.mask_secret(key),
            "uses_platform_credentials": not key and bool(settings.credential_for(tenant.chat.provider)),
        }
    embedding = registry.platform_embedding_spec()
    rerank = registry.platform_rerank_spec()
    return {
        "organization_id": str(org.id),
        "chat": chat,
        "temperature": tenant.temperature if tenant else None,
        "max_response_tokens": tenant.max_response_tokens if tenant else None,
        "allow_platform_fallback": tenant.allow_platform_fallback if tenant else True,
        "effective_chat_models": chain.labels if chain else [],
        "platform_defaults": {
            "chat": registry.platform_chat_spec().label if registry.platform_chat_spec() else None,
            "temperature": settings.temperature,
            "max_response_tokens": settings.max_response_tokens,
            # Read-only: changing these requires re-embedding / is platform-wide.
            "embedding": embedding.label if embedding else None,
            "embedding_dimensions": settings.embedding_dimensions,
            "rerank": rerank.label if rerank else "none",
        },
    }


@router.get("/ai/providers")
async def list_providers(_: User = Depends(get_current_org_admin)):
    """Supported providers and their capabilities. Contains no model names."""
    return {"providers": catalog()}


@router.get("/organization/ai-settings")
async def get_ai_settings(
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    return _public_view(await _target_org(user, organization_id, db))


@router.put("/organization/ai-settings")
async def update_ai_settings(
    body: AISettingsInput,
    request: Request,
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    org = await _target_org(user, organization_id, db)
    previous = _stored(org)
    chat = None
    if body.chat:
        info = provider_info(body.chat.provider)
        if not info.chat_protocol:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{info.label} does not provide chat models")
        base_url = await _effective_endpoint(info.id, body.chat.base_url)
        if body.chat.api_key is None:
            same_provider = previous and previous.chat and previous.chat.provider == info.id
            encrypted = previous.chat.api_key_encrypted if same_provider else None
        elif body.chat.api_key == "":
            encrypted = None
        else:
            encrypted = registry.encrypt_secret(body.chat.api_key.strip())
        if info.requires_api_key and not encrypted and not settings.credential_for(info.id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{info.label} requires an API key")
        chat = registry.TenantChatModel(
            provider=info.id, model=body.chat.model.strip(), base_url=base_url,
            api_key_encrypted=encrypted,
        )
    tenant = registry.TenantAISettings(
        chat=chat,
        temperature=body.temperature,
        max_response_tokens=body.max_response_tokens,
        allow_platform_fallback=body.allow_platform_fallback,
    )
    # Reassign the dict: in-place JSONB mutation is not tracked by SQLAlchemy.
    org.settings = {**(org.settings or {}), "ai": tenant.model_dump(mode="json")}
    audit.record(db, Action.AI_SETTINGS_UPDATED, actor=user, organization_id=org.id,
                 target_type="organization", target_id=org.id,
                 details={"chat_model": f"{chat.provider}:{chat.model}" if chat else "platform default",
                          "own_api_key": bool(chat and chat.api_key_encrypted),
                          "allow_platform_fallback": tenant.allow_platform_fallback},
                 request=request)
    await db.commit()
    registry.invalidate_tenant(org.id)
    logger.info(
        f"AI settings updated: org={org.id} by user={user.id} "
        f"chat={chat.provider + ':' + chat.model if chat else 'platform'}"
    )
    await db.refresh(org)
    return _public_view(org)


@router.delete("/organization/ai-settings")
async def reset_ai_settings(
    request: Request,
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    org = await _target_org(user, organization_id, db)
    org.settings = {k: v for k, v in (org.settings or {}).items() if k != "ai"}
    audit.record(db, Action.AI_SETTINGS_RESET, actor=user, organization_id=org.id,
                 target_type="organization", target_id=org.id, request=request)
    await db.commit()
    registry.invalidate_tenant(org.id)
    logger.info(f"AI settings reset to platform defaults: org={org.id} by user={user.id}")
    await db.refresh(org)
    return _public_view(org)


async def _probe_spec(body: ProbeInput, org: Organization) -> ModelSpec:
    info = provider_info(body.provider)
    base_url = await _effective_endpoint(info.id, body.base_url)
    api_key = body.api_key
    if not api_key:
        stored = _stored(org)
        if stored and stored.chat and stored.chat.provider == info.id:
            api_key = registry.decrypt_secret(stored.chat.api_key_encrypted)
        api_key = api_key or settings.credential_for(info.id)
    return ModelSpec(info.id, body.model or "", api_key, base_url)


def _probe_error(exc: ProviderError) -> dict:
    # Status and category only: provider bodies can echo request details.
    reason = ("billing_or_credits" if exc.billing
              else "rate_limited_or_unavailable" if exc.retryable
              else "unauthorized" if exc.status in (401, 403)
              else "model_not_found" if exc.status == 404
              else "rejected")
    return {"ok": False, "reason": reason, "status": exc.status}


@router.post("/organization/ai-settings/test")
async def test_chat_model(
    body: ProbeInput,
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    """Send one tiny request to verify a model before saving it."""
    if not body.model:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "model is required")
    org = await _target_org(user, organization_id, db)
    spec = await _probe_spec(body, org)
    started = time.perf_counter()
    try:
        result = await build_chat_client(spec).complete(
            [ChatMessage("user", "Reply with the single word: ready")],
            temperature=0.0, max_tokens=16, timeout=20.0,
        )
    except ProviderError as exc:
        return _probe_error(exc)
    return {
        "ok": result.text is not None,
        "reason": None if result.text is not None else "blocked_or_empty",
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "model": spec.label,
    }


@router.post("/organization/ai-settings/models")
async def discover_models(
    body: ProbeInput,
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    """List models available to the given credentials, live from the provider."""
    org = await _target_org(user, organization_id, db)
    spec = await _probe_spec(body, org)
    try:
        models = await build_chat_client(spec).list_models()
    except ProviderError as exc:
        return {**_probe_error(exc), "models": []}
    return {"ok": True, "models": models}
