from __future__ import annotations

import uuid
from contextvars import ContextVar

_correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Retrieve the correlation ID for the current async task context."""
    val = _correlation_id_ctx.get()
    return val if val else ""


def set_correlation_id(correlation_id: str | None = None) -> str:
    """Set the correlation ID for the current context. Generates UUID4 if empty."""
    val = correlation_id.strip() if correlation_id and correlation_id.strip() else str(uuid.uuid4())
    _correlation_id_ctx.set(val)
    return val
