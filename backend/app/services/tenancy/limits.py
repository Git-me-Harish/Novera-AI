"""Per-organization request limits.

Defaults come from settings; a super admin can override any of them for one
organization (stored in organizations.settings["limits"]). The rate limiter
reads them through a short in-process cache so it does not hit the database
on every request.
"""
from __future__ import annotations

import time
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import settings


class OrgLimitOverrides(BaseModel):
    chat_per_minute: Optional[int] = Field(None, ge=1, le=1_000_000)
    upload_per_minute: Optional[int] = Field(None, ge=1, le=1_000_000)
    api_per_minute: Optional[int] = Field(None, ge=1, le=10_000_000)
    # 0 = unlimited
    chat_messages_per_day: Optional[int] = Field(None, ge=0, le=100_000_000)


def defaults() -> dict[str, int]:
    return {
        "chat_per_minute": settings.org_rate_limit_chat_per_minute,
        "upload_per_minute": settings.org_rate_limit_upload_per_minute,
        "api_per_minute": settings.org_rate_limit_api_per_minute,
        "chat_messages_per_day": settings.org_chat_messages_per_day,
    }


def effective_limits(org: Any) -> dict[str, int]:
    overrides = ((getattr(org, "settings", None) or {}).get("limits") or {})
    merged = defaults()
    merged.update({k: v for k, v in overrides.items() if k in merged and v is not None})
    return merged


_CACHE_SECONDS = 60.0
_cache: dict[str, tuple[float, dict[str, int]]] = {}


def invalidate(organization_id: Any) -> None:
    _cache.pop(str(organization_id), None)


async def limits_for(organization_id: Optional[str]) -> dict[str, int]:
    if not organization_id:
        return defaults()
    cached = _cache.get(organization_id)
    if cached and time.monotonic() - cached[0] < _CACHE_SECONDS:
        return cached[1]
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.organization import Organization

    try:
        async with AsyncSessionLocal() as db:
            raw = (await db.execute(
                select(Organization.settings).where(Organization.id == UUID(organization_id))
            )).scalar_one_or_none()
    except Exception:
        return defaults()
    limits = effective_limits(type("Org", (), {"settings": raw or {}})())
    _cache[organization_id] = (time.monotonic(), limits)
    return limits
