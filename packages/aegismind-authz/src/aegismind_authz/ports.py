from __future__ import annotations

from typing import Protocol, runtime_checkable

from aegismind_types import Principal, TokenConsistency
from pydantic import BaseModel, ConfigDict, Field


class RelationshipTuple(BaseModel):
    """Zanzibar relationship tuple representing a directed authorization edge."""

    model_config = ConfigDict(frozen=True)

    resource: str = Field(
        ...,
        description="Resource identifier formatted as type:id, e.g. document:doc_123",
    )
    relation: str = Field(
        ...,
        description="Relation name, e.g. viewer, editor, owner, or folder",
    )
    subject: str = Field(
        ...,
        description="Subject identifier formatted as type:id or type:id#relation",
    )
    caveat: str | None = Field(
        default=None,
        description="Optional conditional caveat expression or context name",
    )


class CheckRequest(BaseModel):
    """Permission evaluation check request."""

    model_config = ConfigDict(frozen=True)

    resource: str = Field(
        ...,
        description="Target resource identifier, e.g. document:doc_123",
    )
    permission: str = Field(
        ...,
        description="Permission or relation to check, e.g. view, edit, or viewer",
    )
    subject: str = Field(
        ...,
        description="Subject string identifier, e.g. user:alice",
    )


@runtime_checkable
class AuthzPort(Protocol):
    """Protocol for Zanzibar-compatible authorization engines (SpiceDB, OpenFGA, Memory)."""

    async def bulk_check(
        self,
        requests: list[CheckRequest],
        consistency: TokenConsistency | None = None,
    ) -> list[bool]:
        """Evaluate a batch of check requests in a single round-trip.

        Args:
            requests: List of CheckRequest objects.
            consistency: Optional token consistency requirement.

        Returns:
            List of booleans matching the index order of input requests.
        """
        ...

    async def write_tuples(
        self,
        tuples: list[RelationshipTuple],
    ) -> TokenConsistency:
        """Write relationship tuples to the authorization engine.

        Args:
            tuples: List of relationship tuples to create or touch.

        Returns:
            TokenConsistency capturing the updated engine revision token.
        """
        ...

    async def delete_tuples(
        self,
        tuples: list[RelationshipTuple],
    ) -> TokenConsistency:
        """Delete relationship tuples from the authorization engine.

        Args:
            tuples: List of relationship tuples to remove.

        Returns:
            TokenConsistency capturing the engine revision token after deletion.
        """
        ...

    async def check_permission(
        self,
        subject: Principal,
        relation: str,
        resource: str,
    ) -> bool:
        """Check whether a single Principal has a relation or permission on a resource.

        Args:
            subject: Principal requesting access.
            relation: Relation or permission to verify.
            resource: Target resource identifier.

        Returns:
            True if permitted, False otherwise.
        """
        ...
