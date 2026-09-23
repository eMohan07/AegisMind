from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from aegismind_core.domain.models import Chunk, ScoredChunk


class VectorStorePort(ABC):
    """Abstract port for vector storage and approximate nearest neighbor search."""

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        limit: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]:
        """Search for top chunks matching the query embedding.

        Args:
            query_embedding: Dense vector representation of query.
            limit: Maximum candidate chunks to retrieve.
            metadata_filter: Optional key-value filter conditions.

        Returns:
            List of ScoredChunk ordered by similarity score descending.
        """
        ...

    @abstractmethod
    async def upsert(self, chunks: list[Chunk]) -> None:
        """Insert or update chunks along with their vector embeddings."""
        ...

    @abstractmethod
    async def delete(self, chunk_ids: list[str]) -> None:
        """Delete chunks by their unique identifiers."""
        ...
