from __future__ import annotations

import logging
import math
from typing import Any

from aegismind_core.domain.models import Chunk, ScoredChunk
from aegismind_core.ports.vector_store import VectorStorePort

logger = logging.getLogger(__name__)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class MemoryVectorStoreAdapter(VectorStorePort):
    """In-memory vector store implementing cosine similarity retrieval."""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        logger.debug("Initialized MemoryVectorStoreAdapter")

    async def upsert(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self._chunks[chunk.id] = chunk
        logger.debug("Upserted %d chunks into memory vector store", len(chunks))

    async def delete(self, chunk_ids: list[str]) -> None:
        for cid in chunk_ids:
            self._chunks.pop(cid, None)
        logger.debug("Deleted %d chunks from memory vector store", len(chunk_ids))

    async def search(
        self,
        query_embedding: list[float],
        limit: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]:
        scored_candidates: list[ScoredChunk] = []

        for chunk in self._chunks.values():
            if chunk.embedding is None:
                continue

            # Check metadata filter if supplied
            if metadata_filter:
                match = all(chunk.metadata.get(k) == v for k, v in metadata_filter.items())
                if not match:
                    continue

            score = _cosine_similarity(query_embedding, chunk.embedding)
            scored_candidates.append(ScoredChunk(chunk=chunk, score=score))

        # Order descending by similarity score
        scored_candidates.sort(key=lambda sc: sc.score, reverse=True)
        return scored_candidates[:limit]
