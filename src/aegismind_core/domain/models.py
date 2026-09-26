from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aegismind_core.domain.permissions import ConsistencyToken
from aegismind_types import Chunk


class User(BaseModel):
    """User identity within AegisMind."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique user identifier")
    tenant_id: str | None = Field(default=None, description="Optional tenant boundary")
    metadata: dict[str, Any] = Field(default_factory=dict)


class Document(BaseModel):
    """Document entity representing an indexed knowledge item."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique document identifier")
    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Full text content of document")
    tenant_id: str | None = Field(default=None, description="Tenant scope")
    folder_id: str | None = Field(default=None, description="Parent folder or hierarchy node")
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """Text chunk derived from a document with optional vector embeddings."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique chunk identifier")
    document_id: str = Field(..., description="Parent document identifier")
    content: str = Field(..., description="Text segment content")
    chunk_index: int = Field(default=0, description="Sequential index within parent document")
    embedding: list[float] | None = Field(
        default=None,
        description="Vector representation for similarity retrieval",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoredChunk(BaseModel):
    """Chunk paired with similarity or relevance score."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    chunk: Chunk = Field(..., description="Retrieved chunk")
    score: float = Field(..., description="Similarity or reranker relevance score")


class RetrievalQuery(BaseModel):
    """Retrieval request specification for access controlled search."""

    model_config = ConfigDict(frozen=True)

    query_text: str = Field(..., description="Text query submitted by user")
    user_id: str = Field(..., description="Identity of caller for Zanzibar checks")
    tenant_id: str | None = Field(default=None, description="Optional tenant isolation scope")
    top_k: int = Field(default=5, ge=1, description="Desired final number of relevant chunks")
    overfetch_factor: float = Field(
        default=4.0,
        ge=3.0,
        le=5.0,
        description="Candidate multiplier between 3 and 5 for permission filtering",
    )
    consistency: ConsistencyToken = Field(
        default_factory=ConsistencyToken,
        description="Zanzibar consistency token with at_least_as_fresh default",
    )
    metadata_filter: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata filtering criteria",
    )


class RetrievalResult(BaseModel):
    """Final response returned from permission guarded retrieval."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    query_text: str
    chunks: list[Any]  # list[ScoredChunk] from either aegismind_retrieval or aegismind_core
    total_candidates_evaluated: int = Field(
        ...,
        description="Total candidates fetched during overfetch phase",
    )
    authorized_candidates_count: int = Field(
        ...,
        description="Number of candidates passing authorization check",
    )
