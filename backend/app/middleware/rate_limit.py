""" Sliding-window rate limiter middleware """
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.net import client_ip
from app.core.redis_manager import redis_manager
from app.services.tenancy.limits import limits_for


@dataclass
class RateRule:
    prefix: str
    limit: int
    window: int
    methods: frozenset[str] = field(default_factory=frozenset)


_RULES: list[RateRule] = [
    # Strict email-action endpoints (5/min)
    RateRule("/api/v1/auth/forgot-password",       5,   60, frozenset({"POST"})),
    RateRule("/api/v1/auth/resend-verification",   5,   60, frozenset({"POST"})),
    # Login brute-force protection (20/min)
    RateRule("/api/v1/auth/login",                20,   60, frozenset({"POST"})),
    # Conversation reads — generous
    RateRule("/api/v1/chat/conversations",        300,  60),
    # LLM calls
    RateRule("/api/v1/chat",                      100,  60, frozenset({"POST"})),
    # Document uploads
    RateRule("/api/v1/documents/upload",           10,  60, frozenset({"POST"})),
    # Document reads/editor
    RateRule("/api/v1/documents",                 300,  60),
    # Everything else
    RateRule("/api/v1/",                          300,  60),
]


def _match_rule(path: str, method: str) -> Optional[RateRule]:
    for rule in _RULES:
        if not path.startswith(rule.prefix):
            continue
        if not rule.methods or method.upper() in rule.methods:
            return rule
    return None


def _principal(request: Request) -> tuple[str, Optional[str]]:
    """(bucket identity, organization id) for the request.

    A signed JWT identifies the user and their organization. The signature is
    verified; expiry is not, because an expired token still names the caller
    for rate-limit purposes (auth rejects it separately). Without a token the
    identity is the client IP, which honours X-Forwarded-For only for the
    configured number of trusted proxies — a client-supplied header used to
    let anyone dodge the login limit by inventing a new IP per request.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            from jose import jwt as jose_jwt

            from app.core.config import settings

            payload = jose_jwt.decode(
                auth[7:], settings.secret_key, algorithms=[settings.algorithm],
                options={"verify_exp": False},
            )
            if payload.get("sub"):
                return f"user:{payload['sub']}", payload.get("organization_id")
        except Exception:
            pass
    return f"ip:{client_ip(request)}", None


def _org_category(path: str, method: str) -> str:
    if method == "POST" and path.rstrip("/") == "/api/v1/chat":
        return "chat"
    if method == "POST" and path.startswith("/api/v1/documents/upload"):
        return "upload"
    return "api"


async def _sliding_window_count(bucket_key: str, window: int) -> int:
    """
    True sliding-window counter using Redis sorted set.

    Each request adds its timestamp as a member score.
    Old entries (outside the window) are pruned before counting.
    Returns the current request count within the window.

    Falls back to the simpler INCR pattern (fixed window) when Redis
    sorted-set commands are unavailable (in-memory fallback).
    """
    now = time.time()
    window_start = now - window
    zset_key = f"rl_sw:{bucket_key}"

    if redis_manager.is_redis_active:
        try:
            pipe = redis_manager._client.pipeline()
            # Remove timestamps outside the window
            pipe.zremrangebyscore(zset_key, "-inf", window_start)
            # Add current timestamp (value = unique float to allow ties)
            # Random suffix: same-microsecond requests must not collapse into one.
            pipe.zadd(zset_key, {f"{now:.6f}:{secrets.token_hex(4)}": now})
            # Count remaining
            pipe.zcard(zset_key)
            # Reset TTL
            pipe.expire(zset_key, window + 1)
            results = await pipe.execute()
            return int(results[2])  # zcard result
        except Exception as e:
            logger.warning(f"Sliding-window ZSET error: {e} — falling back to INCR")

    return await redis_manager.increment(f"rl_fw:{bucket_key}", ttl=window)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    True sliding-window rate limiting via Redis sorted sets.
    Returns HTTP 429 with Retry-After when a limit is exceeded.
    Fails open if Redis is unavailable.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        method = request.method.upper()

        if not path.startswith("/api/"):
            return await call_next(request)

        identifier, organization_id = _principal(request)
        checks: list[tuple[str, str, int, int]] = []  # (scope, bucket, limit, window)

        rule = _match_rule(path, method)
        if rule is not None:
            method_tag = f":{method}" if rule.methods else ""
            checks.append(("user" if identifier.startswith("user:") else "ip",
                           f"{identifier}:{rule.prefix}{method_tag}", rule.limit, rule.window))

        daily_key = None
        daily_limit = 0
        if organization_id:
            limits = await limits_for(organization_id)
            category = _org_category(path, method)
            checks.append(("organization", f"org:{organization_id}:{category}",
                           limits[f"{category}_per_minute"], 60))
            if category == "chat" and limits["chat_messages_per_day"]:
                daily_limit = limits["chat_messages_per_day"]
                daily_key = f"org_day:{organization_id}:chat:{time.strftime('%Y%m%d', time.gmtime())}"

        tightest: Optional[tuple[str, int, int, int]] = None  # scope, limit, remaining, window
        for scope, bucket, limit, window in checks:
            try:
                count = await _sliding_window_count(bucket, window)
            except Exception as exc:
                # Availability over strictness: a Redis outage must not take the API down.
                logger.warning(f"Rate limit check error ({scope}): {type(exc).__name__} — allowing")
                continue
            if count > limit:
                logger.warning(f"Rate limit exceeded: {scope} {bucket} ({count}/{limit} in {window}s)")
                return _too_many(scope, limit, window,
                                 f"Rate limit exceeded: max {limit} requests per {window} seconds"
                                 + (" for your organization." if scope == "organization" else "."))
            remaining = max(0, limit - count)
            if tightest is None or remaining < tightest[2]:
                tightest = (scope, limit, remaining, window)

        if daily_key:
            try:
                used = await redis_manager.increment(daily_key, ttl=2 * 86400)
            except Exception:
                used = 0
            if used > daily_limit:
                seconds_left = 86400 - int(time.time()) % 86400
                return _too_many("organization_daily", daily_limit, seconds_left,
                                 "Your organization has used today's chat allowance.")

        response = await call_next(request)
        if tightest is not None:
            scope, limit, remaining, window = tightest
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + window)
            response.headers["X-RateLimit-Scope"] = scope
        return response


def _too_many(scope: str, limit: int, retry_after: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "Too Many Requests", "detail": message, "message": message, "scope": scope,
                 "retry_after": retry_after},
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + retry_after),
            "X-RateLimit-Scope": scope,
        },
    )
