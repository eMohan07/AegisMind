from __future__ import annotations

from abc import ABC, abstractmethod

from aegismind_core.domain.permissions import (
    AuthzDecision,
    ConsistencyToken,
    PermissionCheck,
    Resource,
    Subject,
)


class AuthzPort(ABC):
    """Abstract port for Zanzibar-compatible authorization engines (e.g. SpiceDB)."""

    @abstractmethod
    async def check(
        self,
        check: PermissionCheck,
        consistency: ConsistencyToken | None = None,
    ) -> AuthzDecision:
        """Evaluate a single subject-permission-resource tuple.

        Args:
            check: The permission check specification.
            consistency: Consistency requirement, defaulting to at_least_as_fresh.

        Returns:
            AuthzDecision containing whether access is permitted.
        """
        ...

    @abstractmethod
    async def bulk_check(
        self,
        checks: list[PermissionCheck],
        consistency: ConsistencyToken | None = None,
    ) -> list[AuthzDecision]:
        """Evaluate multiple subject-permission-resource tuples in a single call.

        Args:
            checks: List of permission check specifications.
            consistency: Consistency requirement, defaulting to at_least_as_fresh.

        Returns:
            List of AuthzDecision objects matching the input order.
        """
        ...

    @abstractmethod
    async def write_relationship(
        self,
        subject: Subject,
        relation: str,
        resource: Resource,
    ) -> str:
        """Write a relationship tuple to the authorization engine.

        Returns:
            Zed token string representing the state of the write.
        """
        ...

    @abstractmethod
    async def delete_relationship(
        self,
        subject: Subject,
        relation: str,
        resource: Resource,
    ) -> str:
        """Delete a relationship tuple from the authorization engine.

        Returns:
            Zed token string representing the state after deletion.
        """
        ...
