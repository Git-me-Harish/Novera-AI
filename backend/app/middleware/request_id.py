"""
Request correlation ID middleware.

Injects a unique X-Request-ID header into every request and response.
When present in the incoming request (e.g. from Render's load balancer or
a frontend that sets it), the existing value is reused so the ID flows
end-to-end through logs, error reports, and client retries.

Usage in logs:
  Every logger.info/error/warning call inside a request will automatically
  include the request ID via loguru's contextualize(), making it trivial to
  grep all log lines for a single request across multiple workers:

    grep "req_id=abc123" logs/novera.log

The ID is also exposed as X-Request-ID in the response so the frontend can
include it in bug reports / Sentry breadcrumbs.
"""
from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from loguru import logger


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request and response."""

    HEADER = "X-Request-ID"

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Reuse client-supplied ID if present and valid, otherwise generate one
        req_id = request.headers.get(self.HEADER, "").strip()
        if not req_id or len(req_id) > 64:
            req_id = str(uuid.uuid4())

        # Store on request state so endpoints can read it if needed
        request.state.request_id = req_id

        # Bind to loguru context for the duration of this request
        with logger.contextualize(request_id=req_id):
            response: Response = await call_next(request)

        # Echo the ID back in the response
        response.headers[self.HEADER] = req_id
        return response


__all__ = ["RequestIDMiddleware"]
