from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from aegismind_core.observability.context import get_correlation_id
from aegismind_core.observability.tracing import current_span_id, current_trace_id


class JsonLogFormatter(logging.Formatter):
    """Structured JSON formatter with correlation ID, trace ID, and span ID."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None) or get_correlation_id(),
            "trace_id": current_trace_id(),
            "span_id": current_span_id(),
        }

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_payload["stack_info"] = self.formatStack(record.stack_info)

        # Include standard extra fields if present
        standard_attrs = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "correlation_id",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                try:
                    json.dumps(value)
                    log_payload[key] = value
                except (TypeError, OverflowError):
                    log_payload[key] = str(value)

        return json.dumps(log_payload, default=str)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configure root logger to output structured JSON format to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing stream handlers to avoid duplicate log emission
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    root_logger.addHandler(handler)
