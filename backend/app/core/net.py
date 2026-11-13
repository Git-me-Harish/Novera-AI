"""Client network identity behind a known number of reverse proxies."""
from __future__ import annotations

from starlette.requests import Request

from app.core.config import settings


def client_ip(request: Request) -> str:
    """The real client address.

    X-Forwarded-For is client-controlled except for the entries our own
    proxies append. With N trusted proxies the client is the N-th entry from
    the right; anything further left could be forged. With no trusted proxy
    the socket peer is the only trustworthy address.
    """
    hops = settings.trusted_proxy_hops
    peer = request.client.host if request.client else "unknown"
    if hops <= 0:
        return peer
    forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
    if len(forwarded) >= hops:
        return forwarded[-hops]
    return peer
