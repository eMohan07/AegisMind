from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    FAILED = "failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Proposal(BaseModel):
    """A proposal for an action requiring human approval before execution."""

    model_config = ConfigDict(frozen=False)

    id: str = Field(
        default_factory=lambda: f"prop_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"
    )
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str = Field(
        default_factory=lambda: (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    )
    status: ProposalStatus = Field(default=ProposalStatus.PENDING)
    tool_name: str = Field(..., description="Name of the tool to be executed")
    args: dict[str, Any] = Field(default_factory=dict, description="Original tool arguments")
    edited_args: dict[str, Any] | None = Field(
        default=None, description="Edited arguments after approval"
    )
    risk: RiskLevel = Field(default=RiskLevel.LOW, description="Risk level of the action")
    reasoning: str = Field(default="", description="Why the agent wants to execute this")
    source_refs: list[str] = Field(
        default_factory=list, description="Source references for the action"
    )
    preview: str = Field(default="", description="Preview of the action (diff or argv)")
    tainted: bool = Field(default=False, description="Whether the action is tainted")
    taint_sources: list[str] = Field(default_factory=list, description="Sources of taint")
    decision_reason: str | None = Field(default=None, description="Reason for the decision")
    result: str | None = Field(default=None, description="Result of execution after approval")

    def elevate_risk(self) -> None:
        """Elevate risk by one level."""
        if self.risk == RiskLevel.LOW:
            self.risk = RiskLevel.MEDIUM
        elif self.risk == RiskLevel.MEDIUM:
            self.risk = RiskLevel.HIGH

    def is_expired(self) -> bool:
        """Check if the proposal has expired."""
        return datetime.now(UTC) > datetime.fromisoformat(self.expires_at)
