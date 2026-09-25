from __future__ import annotations

from aegismind_retrieval.ports import TelemetryPort


class NoOpTelemetryAdapter(TelemetryPort):
    """Default no-op telemetry adapter for retrieval operations."""

    def record_stage_latency(self, stage: str, duration_seconds: float) -> None:
        """No-op stage latency recording."""

    def record_reranker_latency(self, duration_seconds: float) -> None:
        """No-op reranker latency recording."""

    def record_authz_metrics(self, tenant_id: str, evaluated: int, denied: int) -> None:
        """No-op authz metrics recording."""

    def record_overfetch_effectiveness(self, tenant_id: str, ratio: float) -> None:
        """No-op overfetch effectiveness recording."""
