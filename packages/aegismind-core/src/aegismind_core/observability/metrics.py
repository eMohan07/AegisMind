from __future__ import annotations

import logging

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)

# Prometheus metrics definitions
AUTHZ_CHUNKS_EVALUATED = Counter(
    "aegismind_authz_chunks_evaluated_total",
    "Total candidate chunks evaluated against Zanzibar ReBAC policies per tenant",
    ["tenant_id"],
)

AUTHZ_CHUNKS_DENIED = Counter(
    "aegismind_authz_chunks_denied_total",
    "Total candidate chunks denied by Zanzibar ReBAC authorization per tenant",
    ["tenant_id"],
)

AUTHZ_DENY_RATE = Gauge(
    "aegismind_authz_deny_rate",
    "Instantaneous ratio of candidate chunks denied by Zanzibar ReBAC per tenant",
    ["tenant_id"],
)

OVERFETCH_EFFECTIVENESS = Gauge(
    "aegismind_overfetch_effectiveness",
    "Ratio of chunks passing Zanzibar ReBAC relative to total candidates evaluated",
    ["tenant_id"],
)

RERANKER_LATENCY_SECONDS = Histogram(
    "aegismind_reranker_latency_seconds",
    "Histogram of cross-encoder reranker call durations in seconds",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

QUERY_LATENCY_SECONDS = Histogram(
    "aegismind_query_latency_seconds",
    "Histogram of end-to-end retrieval query latency broken down by stage",
    ["stage"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


def record_authz_evaluation(tenant_id: str, evaluated: int, denied: int) -> None:
    """Record candidate chunk evaluation and calculate tenant deny rate."""
    tid = tenant_id or "default"
    AUTHZ_CHUNKS_EVALUATED.labels(tenant_id=tid).inc(evaluated)
    AUTHZ_CHUNKS_DENIED.labels(tenant_id=tid).inc(denied)
    rate = denied / max(1, evaluated)
    AUTHZ_DENY_RATE.labels(tenant_id=tid).set(rate)


def record_overfetch_ratio(tenant_id: str, ratio: float) -> None:
    """Record overfetch effectiveness ratio and alert if below 0.3 threshold."""
    tid = tenant_id or "default"
    clamped_ratio = max(0.0, min(1.0, float(ratio)))
    OVERFETCH_EFFECTIVENESS.labels(tenant_id=tid).set(clamped_ratio)
    if clamped_ratio < 0.3:
        logger.warning(
            "[ALERT] aegismind_overfetch_effectiveness dropped below 0.3 threshold "
            "(current=%.4f, tenant='%s')",
            clamped_ratio,
            tid,
            extra={"tenant_id": tid, "effectiveness": clamped_ratio, "alert": "low_overfetch"},
        )


def record_reranker_duration(duration_seconds: float) -> None:
    """Record duration of cross-encoder reranker execution."""
    RERANKER_LATENCY_SECONDS.observe(max(0.0, duration_seconds))


def record_stage_duration(stage: str, duration_seconds: float) -> None:
    """Record latency of individual retrieval pipeline stages."""
    QUERY_LATENCY_SECONDS.labels(stage=stage).observe(max(0.0, duration_seconds))


def render_prometheus_metrics(registry: CollectorRegistry = REGISTRY) -> bytes:
    """Render all registered Prometheus metrics into standard text exposition format."""
    return generate_latest(registry)
