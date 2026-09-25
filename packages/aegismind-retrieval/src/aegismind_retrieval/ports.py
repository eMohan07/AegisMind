from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from aegismind_types import ChatTurn, Chunk
from pydantic import BaseModel, ConfigDict, Field


class ScoredChunk(BaseModel):
    """Chunk paired with a similarity, fusion, or reranking score."""

    model_config = ConfigDict(frozen=True)

    chunk: Chunk = Field(..., description="Retrieved chunk payload")
    score: float = Field(..., description="Relevance or similarity score")


@runtime_checkable
class QueryRewriterPort(Protocol):
    """Port for conversational query rewriting against chat history."""

    async def rewrite_query(
        self,
        query: str,
        history: list[ChatTurn] | None = None,
    ) -> str:
        """Resolve pronouns and coreferences against conversational history.

        Args:
            query: The incoming user query string.
            history: Optional conversational history turns.
        """
        ...


@runtime_checkable
class VectorStorePort(Protocol):
    """Port for indexing and querying dense and sparse chunk vectors."""

    async def upsert(self, chunks: list[Chunk]) -> None:
        """Insert or update chunks with dense or sparse embeddings."""
        ...

    async def query_dense(
        self,
        vector: list[float],
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Query vector store using dense vector representation with tenant scoping."""
        ...

    async def query_lexical(
        self,
        query_text: str,
        sparse_vector: dict[int, float] | None = None,
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Query vector store using lexical BM25 or full-text search with tenant scoping."""
        ...

    async def query(
        self,
        vector: list[float] | None = None,
        sparse_vector: dict[int, float] | None = None,
        pre_filter: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Query vector store using hybrid dense and sparse representations.

        Args:
            vector: Query dense embedding.
            sparse_vector: Query sparse lexical token weights.
            pre_filter: Metadata filter (e.g. tenant_id, security groups).
            top_k: Maximum number of scored candidates to return.
        """
        ...

    async def delete(self, chunk_ids: list[str]) -> bool:
        """Delete chunks by ID. Returns True if deleted."""
        ...

    async def get_by_document(self, document_id: str) -> list[Chunk]:
        """Retrieve all active chunks for a document to check content hashes."""
        ...

    async def soft_delete_document(self, document_id: str) -> int:
        """Mark existing chunks for a document as tombstoned."""
        ...

    async def vacuum_tombstones(self, older_than_seconds: int = 86400) -> int:
        """Permanently hard-delete tombstoned chunks older than threshold."""
        ...


@runtime_checkable
class EmbedderPort(Protocol):
    """Port for generating dense and sparse vector embeddings."""

    async def embed_query(self, query: str) -> list[float]:
        """Generate dense vector embedding for a search query string."""
        ...

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        """Generate dense vector embeddings for a list of document strings."""
        ...

    async def embed_sparse_query(self, query: str) -> dict[int, float]:
        """Generate sparse lexical token weights for a query string."""
        ...

    async def embed_sparse_documents(self, documents: list[str]) -> list[dict[int, float]]:
        """Generate sparse lexical token weights for a list of document strings."""
        ...


@runtime_checkable
class RerankerPort(Protocol):
    """Port for cross-encoder reranking of retrieved candidate chunks."""

    async def rerank(
        self,
        query: str,
        candidates: list[ScoredChunk],
        top_n: int,
    ) -> list[ScoredChunk]:
        """Rerank candidates based on deep query-document cross-attention.

        Args:
            query: The original search query string.
            candidates: Pre-filtered list of scored candidate chunks.
            top_n: Number of top reranked chunks to return.
        """
        ...


@runtime_checkable
class TelemetryPort(Protocol):
    """Port for recording telemetry metrics and distributed tracing spans."""

    def record_stage_latency(self, stage: str, duration_seconds: float) -> None:
        """Record latency for a specific retrieval lifecycle stage in seconds."""
        ...

    def record_reranker_latency(self, duration_seconds: float) -> None:
        """Record cross-encoder reranker execution duration in seconds."""
        ...

    def record_authz_metrics(self, tenant_id: str, evaluated: int, denied: int) -> None:
        """Record Zanzibar authorization candidate evaluation counts."""
        ...

    def record_overfetch_effectiveness(self, tenant_id: str, ratio: float) -> None:
        """Record ratio of authorized candidates to total candidates evaluated."""
        ...
