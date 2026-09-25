from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

_initialized: bool = False


def init_tracing(service_name: str = "aegismind-core") -> TracerProvider:
    """Initialize OpenTelemetry TracerProvider if not already configured."""
    global _initialized
    current_provider = trace.get_tracer_provider()
    if not _initialized:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
        _initialized = True
        return provider
    if isinstance(current_provider, TracerProvider):
        return current_provider
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    trace.set_tracer_provider(provider)
    _initialized = True
    return provider


def get_tracer(name: str = "aegismind") -> trace.Tracer:
    """Return an OpenTelemetry tracer instance."""
    return trace.get_tracer(name)


def current_trace_id() -> str | None:
    """Return current trace ID formatted as a 32-character hex string if active."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid and ctx.trace_id != 0:
        return format(ctx.trace_id, "032x")
    return None


def current_span_id() -> str | None:
    """Return current span ID formatted as a 16-character hex string if active."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid and ctx.span_id != 0:
        return format(ctx.span_id, "016x")
    return None


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[trace.Span]:
    """Context manager to execute a code block within an active OpenTelemetry span."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, v)
        yield span
