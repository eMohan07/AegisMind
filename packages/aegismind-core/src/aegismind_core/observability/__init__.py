from __future__ import annotations

from aegismind_core.observability.adapter import PrometheusTelemetryAdapter
from aegismind_core.observability.context import get_correlation_id, set_correlation_id
from aegismind_core.observability.logging import JsonLogFormatter, setup_structured_logging
from aegismind_core.observability.metrics import (
    AUTHZ_CHUNKS_DENIED,
    AUTHZ_CHUNKS_EVALUATED,
    AUTHZ_DENY_RATE,
    OVERFETCH_EFFECTIVENESS,
    QUERY_LATENCY_SECONDS,
    RERANKER_LATENCY_SECONDS,
    record_authz_evaluation,
    record_overfetch_ratio,
    record_reranker_duration,
    record_stage_duration,
    render_prometheus_metrics,
)
from aegismind_core.observability.middleware import CorrelationIdAndTracingMiddleware
from aegismind_core.observability.tracing import (
    current_span_id,
    current_trace_id,
    get_tracer,
    init_tracing,
    trace_span,
)

__all__ = [
    "AUTHZ_CHUNKS_DENIED",
    "AUTHZ_CHUNKS_EVALUATED",
    "AUTHZ_DENY_RATE",
    "CorrelationIdAndTracingMiddleware",
    "JsonLogFormatter",
    "OVERFETCH_EFFECTIVENESS",
    "PrometheusTelemetryAdapter",
    "QUERY_LATENCY_SECONDS",
    "RERANKER_LATENCY_SECONDS",
    "current_span_id",
    "current_trace_id",
    "get_correlation_id",
    "get_tracer",
    "init_tracing",
    "record_authz_evaluation",
    "record_overfetch_ratio",
    "record_reranker_duration",
    "record_stage_duration",
    "render_prometheus_metrics",
    "set_correlation_id",
    "setup_structured_logging",
    "trace_span",
]
