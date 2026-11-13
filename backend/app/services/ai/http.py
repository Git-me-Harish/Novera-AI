"""Shared HTTP transport with uniform provider error classification."""
from __future__ import annotations

import re
from typing import Any, Optional

import httpx

from .types import ProviderError

_BILLING_MARKERS = (
    "credit", "billing", "insufficient_quota", "payment", "prepayment",
    "exceeded your current quota", "account is not active",
)

_client: Optional[httpx.AsyncClient] = None


def client() -> httpx.AsyncClient:
    """One pooled client per process; per-call timeouts are passed explicitly."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _retry_after(response: httpx.Response) -> Optional[float]:
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    match = re.search(r"retry[_ ]in\s+([\d.]+)s", response.text or "", re.IGNORECASE)
    return float(match.group(1)) if match else None


def classify(provider: str, response: httpx.Response) -> ProviderError:
    """Turn a non-2xx response into a ProviderError without leaking secrets."""
    body = (response.text or "")[:500]
    lowered = body.lower()
    status = response.status_code
    billing = status == 402 or (
        status in (403, 429) and any(marker in lowered for marker in _BILLING_MARKERS)
    )
    retryable = not billing and (status == 429 or status == 408 or status >= 500)
    return ProviderError(
        f"{provider} returned HTTP {status}: {body}",
        provider=provider,
        status=status,
        retryable=retryable,
        billing=billing,
        retry_after=_retry_after(response) if retryable else None,
    )


async def post_json(
    provider: str,
    url: str,
    *,
    json: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    try:
        response = await client().post(url, json=json, headers=headers, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise ProviderError(f"{provider} timed out", provider=provider, retryable=True) from exc
    except httpx.TransportError as exc:
        raise ProviderError(
            f"{provider} connection failed: {type(exc).__name__}", provider=provider, retryable=True
        ) from exc
    if response.status_code >= 400:
        raise classify(provider, response)
    return response.json()


async def get_json(
    provider: str, url: str, *, headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    try:
        response = await client().get(url, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"{provider} request failed: {type(exc).__name__}", provider=provider, retryable=True
        ) from exc
    if response.status_code >= 400:
        raise classify(provider, response)
    return response.json()
