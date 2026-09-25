from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, runtime_checkable

from aegismind_types import Chunk, Document, Record
from pydantic import BaseModel, ConfigDict, Field


class IngestionSummary(BaseModel):
    """Execution summary statistics from an ingestion run."""

    model_config = ConfigDict(frozen=True)

    records_ingested: int = Field(default=0, description="Total source records processed")
    documents_created: int = Field(default=0, description="Total normalized documents parsed")
    chunks_indexed: int = Field(default=0, description="Total chunks indexed into vector store")
    tuples_written: int = Field(
        default=0,
        description="Total Zanzibar relationship tuples written to Authz",
    )
    errors: list[str] = Field(default_factory=list, description="Non-fatal warning or error logs")


@runtime_checkable
class ParserPort(Protocol):
    """Port for parsing raw ingested records into canonical Documents."""

    async def parse(self, record: Record) -> Document:
        """Parse raw record payload into normalized Document."""
        ...


@runtime_checkable
class ChunkerPort(Protocol):
    """Port for segmenting Document content into contextualized chunks."""

    def chunk(self, document: Document) -> list[Chunk]:
        """Segment a Document into a list of Chunk models."""
        ...


@runtime_checkable
class IngestionPipelinePort(Protocol):
    """Port for executing the end-to-end ingestion and indexing pipeline."""

    async def ingest_records(self, records: list[Record]) -> IngestionSummary:
        """Ingest a batch of records through parsing, chunking, embedding, and authz."""
        ...


class DLQItem(BaseModel):
    """Dead-letter queue record representing a failed ingestion sync item."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    connector_id: str = Field(..., description="Source connector identifier")
    resource_id: str = Field(..., description="Identifier of the failed source resource")
    error_message: str = Field(..., description="Failure description or traceback summary")
    payload: dict[str, Any] = Field(default_factory=dict, description="Raw record payload")
    retry_count: int = Field(default=0, description="Number of retry attempts made")
    status: Literal["pending", "retried", "resolved", "abandoned"] = Field(
        default="pending", description="Processing lifecycle state"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_failed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class DLQPort(Protocol):
    """Port for Dead-Letter Queue persistence and retry management."""

    async def enqueue(
        self,
        connector_id: str,
        resource_id: str,
        error_message: str,
        payload: dict[str, Any] | None = None,
    ) -> DLQItem:
        """Enqueue a failed connector item into the dead-letter queue."""
        ...

    async def list_items(
        self,
        connector_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[DLQItem]:
        """List DLQ items with optional filters."""
        ...

    async def get_item(self, item_id: str) -> DLQItem | None:
        """Fetch a specific DLQ item by ID."""
        ...

    async def update_status(
        self,
        item_id: str,
        status: Literal["pending", "retried", "resolved", "abandoned"],
        error_message: str | None = None,
    ) -> DLQItem | None:
        """Update item lifecycle status and increment retry count."""
        ...

    async def delete_item(self, item_id: str) -> bool:
        """Permanently delete or purge an item from the dead-letter queue."""
        ...
