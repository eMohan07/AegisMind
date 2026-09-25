from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from aegismind_core.observability.context import set_correlation_id
from aegismind_core.observability.tracing import get_tracer

logger = logging.getLogger(__name__)


class CorrelationIdAndTracingMiddleware(BaseHTTPMiddleware):
    """Middleware extracting or generating correlation ID and maintaining trace context."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        header_cid = request.headers.get("X-Correlation-ID") or request.headers.get(
            "x-correlation-id"
        )
        correlation_id = set_correlation_id(header_cid)

        tracer = get_tracer()
        span_name = f"agora.http {request.method} {request.url.path}"
        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.path", request.url.path)
            span.set_attribute("correlation_id", correlation_id)

            try:
                response = await call_next(request)
                span.set_attribute("http.status_code", response.status_code)
                response.headers["X-Correlation-ID"] = correlation_id
                return response
            except Exception as exc:
                span.record_exception(exc)
                span.set_attribute("http.status_code", 500)
                logger.error(
                    "Unhandled exception in request %s %s: %s",
                    request.method,
                    request.url.path,
                    exc,
                    exc_info=True,
                )
                raise
