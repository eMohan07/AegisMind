from __future__ import annotations

from typing import Protocol, runtime_checkable

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
