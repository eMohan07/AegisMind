from __future__ import annotations

from abc import ABC, abstractmethod

from aegismind_core.domain.models import ScoredChunk


class RerankerPort(ABC):
    """Abstract port for reranking candidate chunks against a query."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[ScoredChunk],
        top_k: int,
    ) -> list[ScoredChunk]:
        """Score and reorder candidate chunks, truncating to top_k.

        Args:
            query: The search query text.
            candidates: Allowed candidate chunks after authorization filtering.
            top_k: Desired final output count.

        Returns:
            List of ScoredChunk ordered by relevance descending, up to top_k elements.
        """
        ...
