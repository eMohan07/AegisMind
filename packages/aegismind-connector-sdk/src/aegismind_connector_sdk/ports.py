from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from aegismind_types import Record
from pydantic import BaseModel, ConfigDict, Field


class ConnectorSpec(BaseModel):
    """Specification describing connector metadata, capabilities, and configuration schema."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Unique connector name identifier")
    version: str = Field(default="0.0.1", description="Connector release version")
    documentation_url: str | None = Field(
        default=None,
        description="Link to connector setup and documentation",
    )
    config_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema defining required connector configuration",
    )
    supports_incremental: bool = Field(
        default=False,
        description="Whether connector supports cursor-based incremental sync",
    )
    supported_destination_sync_modes: list[str] = Field(
        default_factory=lambda: ["full_refresh", "incremental"],
        description="Sync modes supported by this connector",
    )


@runtime_checkable
class ConnectorPort(Protocol):
    """Core protocol defining the contract for all AegisMind ingestion connectors."""

    def spec(self) -> ConnectorSpec:
        """Return the connector specification and schema metadata."""
        ...

    async def check(self) -> bool:
        """Verify connectivity, credentials, and source availability."""
        ...

    def read(
        self,
        state: dict[str, Any] | None = None,
    ) -> AsyncIterator[Record]:
        """Read records incrementally or fully from source data stream.

        Args:
            state: Optional state dictionary holding cursor values from previous sync.

        Yields:
            Record instances ready for ingestion and indexing.
        """
        ...
