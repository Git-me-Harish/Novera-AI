""" Sliding-window rate limiter middleware """
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.redis_manager import redis_manager


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


def _extract_identifier(request: Request) -> str:
    """
    Stable, abuse-resistant request identifier for rate-limit bucket.

    1. Verified JWT sub (authenticated users → per-user bucket)
    2. X-Forwarded-For first hop (behind Render proxy)
    3. Direct peer IP
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            from jose import jwt as jose_jwt, ExpiredSignatureError
            from app.core.config import settings
            payload = jose_jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.algorithm],
                options={"verify_exp": False},
            )
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"

    return f"ip:{request.client.host}" if request.client else "ip:unknown"


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
            pipe.zadd(zset_key, {f"{now:.6f}": now})
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
        method = request.method

        if not path.startswith("/api/"):
            return await call_next(request)

        rule = _match_rule(path, method)
        if rule is None:
            return await call_next(request)

        identifier = _extract_identifier(request)
        method_tag = f":{method.upper()}" if rule.methods else ""
        bucket_key = f"{identifier}:{rule.prefix}{method_tag}"

        try:
            count = await _sliding_window_count(bucket_key, rule.window)
        except Exception as exc:
            logger.warning(f"Rate limit check error: {exc} — allowing request")
            return await call_next(request)

        remaining = max(0, rule.limit - count)
        reset_at = int(time.time()) + rule.window

        if count > rule.limit:
            logger.warning(
                f"Rate limit exceeded: {identifier} on {method} {rule.prefix} "
                f"({count}/{rule.limit} in {rule.window}s)"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": (
                        f"Rate limit exceeded. "
                        f"Max {rule.limit} requests per {rule.window} seconds."
                    ),
                    "retry_after": rule.window,
                },
                headers={
                    "Retry-After": str(rule.window),
                    "X-RateLimit-Limit": str(rule.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rule.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response


__all__ = ["RateLimitMiddleware"]