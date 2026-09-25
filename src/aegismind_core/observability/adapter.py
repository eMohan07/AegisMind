from __future__ import annotations

from aegismind_retrieval.ports import TelemetryPort

from aegismind_core.observability.metrics import (
    record_authz_evaluation,
    record_overfetch_ratio,
    record_reranker_duration,
    record_stage_duration,
)


class PrometheusTelemetryAdapter(TelemetryPort):
    """Concrete adapter connecting retrieval pipeline lifecycle events to Prometheus."""

    def record_stage_latency(self, stage: str, duration_seconds: float) -> None:
        """Record stage execution duration in Prometheus histogram."""
        record_stage_duration(stage=stage, duration_seconds=duration_seconds)

    def record_reranker_latency(self, duration_seconds: float) -> None:
        """Record cross-encoder reranker execution duration in Prometheus histogram."""
        record_reranker_duration(duration_seconds=duration_seconds)

    def record_authz_metrics(self, tenant_id: str, evaluated: int, denied: int) -> None:
        """Record evaluated and denied candidate counts in Prometheus counters and gauge."""
        record_authz_evaluation(tenant_id=tenant_id, evaluated=evaluated, denied=denied)

    def record_overfetch_effectiveness(self, tenant_id: str, ratio: float) -> None:
        """Record overfetch ratio in Prometheus gauge and check alert threshold."""
        record_overfetch_ratio(tenant_id=tenant_id, ratio=ratio)
