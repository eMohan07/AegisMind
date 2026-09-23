from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ConsistencyRequirement(StrEnum):
    """Consistency level requested for authorization checks."""

    MINIMIZE_LATENCY = "minimize_latency"
    AT_LEAST_AS_FRESH = "at_least_as_fresh"
    FULLY_CONSISTENT = "fully_consistent"


class ConsistencyToken(BaseModel):
    """Consistency token representing SpiceDB or Zanzibar zed tokens.

    Enables causal consistency across writes and subsequent reads.
    """

    model_config = ConfigDict(frozen=True)

    requirement: ConsistencyRequirement = ConsistencyRequirement.AT_LEAST_AS_FRESH
    token: str | None = Field(
        default=None,
        description="Zed token string when using at_least_as_fresh consistency.",
    )


class Subject(BaseModel):
    """Subject requesting permission (e.g., user:alice)."""

    model_config = ConfigDict(frozen=True)

    type: str = Field(default="user", description="Subject type, e.g. user or service_account")
    id: str = Field(..., description="Unique subject identifier")
    relation: str | None = Field(
        default=None,
        description="Optional relation for subject sets, e.g. group:engineering#member",
    )

    def to_string(self) -> str:
        """Serialize subject to Zanzibar string notation."""
        if self.relation:
            return f"{self.type}:{self.id}#{self.relation}"
        return f"{self.type}:{self.id}"


class Resource(BaseModel):
    """Resource being accessed (e.g., document:doc_123)."""

    model_config = ConfigDict(frozen=True)

    type: str = Field(default="document", description="Resource type, e.g. document or folder")
    id: str = Field(..., description="Unique resource identifier")

    def to_string(self) -> str:
        """Serialize resource to Zanzibar string notation."""
        return f"{self.type}:{self.id}"


class PermissionCheck(BaseModel):
    """Authorization check request payload."""

    model_config = ConfigDict(frozen=True)

    subject: Subject
    permission: str = Field(
        default="view",
        description="Permission to verify, such as view, edit, or manage",
    )
    resource: Resource


class AuthzDecision(BaseModel):
    """Result of an individual authorization check."""

    model_config = ConfigDict(frozen=True)

    permitted: bool
    reason: str | None = None
