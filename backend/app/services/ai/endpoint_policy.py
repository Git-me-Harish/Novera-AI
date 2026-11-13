"""SSRF guard for model endpoints supplied by tenants."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import settings


class EndpointNotAllowed(ValueError):
    pass


def _is_private(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified)


async def validate_tenant_endpoint(url: str) -> str:
    """Return the normalized URL, or raise EndpointNotAllowed.

    Every address the host resolves to is checked, so a public name that
    points at 169.254.169.254 or 10.x is rejected too.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise EndpointNotAllowed("Endpoint must be an http(s) URL with a host")
    if parsed.username or parsed.password:
        raise EndpointNotAllowed("Put credentials in the API key field, not the URL")
    if settings.ai_allow_private_tenant_endpoints:
        return url.strip().rstrip("/")
    if parsed.scheme != "https":
        raise EndpointNotAllowed("Endpoint must use https")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise EndpointNotAllowed("Endpoint host does not resolve") from exc
    if any(_is_private(info[4][0]) for info in infos):
        raise EndpointNotAllowed("Endpoint resolves to a private or internal address")
    return url.strip().rstrip("/")
