from __future__ import annotations

import logging

from aegismind_core.domain.models import ScoredChunk
from aegismind_core.ports.reranker import RerankerPort

logger = logging.getLogger(__name__)


class MockRerankerAdapter(RerankerPort):
    """Mock reranker adapter scoring by token overlap and existing score."""

    def __init__(self, lexical_boost: float = 0.5) -> None:
        self.lexical_boost = lexical_boost
        logger.debug(
            "Initialized MockRerankerAdapter with lexical_boost=%.2f",
            lexical_boost,
        )

    async def rerank(
        self,
        query: str,
        candidates: list[ScoredChunk],
        top_n: int,
    ) -> list[ScoredChunk]:
        query_words = set(query.lower().split())
        reranked: list[ScoredChunk] = []

        for candidate in candidates:
            content_words = set(candidate.chunk.content.lower().split())
            overlap = len(query_words.intersection(content_words)) / max(len(query_words), 1)
            combined_score = candidate.score + (overlap * self.lexical_boost)
            reranked.append(ScoredChunk(chunk=candidate.chunk, score=round(combined_score, 4)))

        reranked.sort(key=lambda sc: sc.score, reverse=True)
        return reranked[:top_n]
