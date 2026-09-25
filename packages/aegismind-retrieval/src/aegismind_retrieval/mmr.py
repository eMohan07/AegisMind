from __future__ import annotations

import logging
from collections.abc import Sequence

from aegismind_types import Chunk

from aegismind_retrieval.ports import ScoredChunk

logger = logging.getLogger(__name__)

DEFAULT_LAMBDA_MULT: float = 0.7


def _chunk_content_similarity(chunk_a: Chunk, chunk_b: Chunk) -> float:
    """Compute lexical Jaccard similarity and document identity penalty between two chunks."""
    # Chunks from identical document have inherent baseline redundancy
    same_doc_boost = 0.3 if chunk_a.document_id == chunk_b.document_id else 0.0

    words_a = set(chunk_a.content.lower().split())
    words_b = set(chunk_b.content.lower().split())
    if not words_a or not words_b:
        return same_doc_boost

    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    jaccard = intersection / union if union > 0 else 0.0
    return min(1.0, (1.0 - same_doc_boost) * jaccard + same_doc_boost)


def maximal_marginal_relevance(
    candidates: Sequence[ScoredChunk],
    top_n: int,
    lambda_mult: float = DEFAULT_LAMBDA_MULT,
) -> list[ScoredChunk]:
    """Reorder reranked candidates using Maximal Marginal Relevance (MMR).

    Prevents final top_k from being dominated by near-duplicate chunks from the same document.

    Args:
        candidates: List of ScoredChunk instances ordered by reranker score.
        top_n: Number of diverse chunks to return.
        lambda_mult: Diversity parameter between 0.0 (maximum diversity) and 1.0 (pure relevance).

    Returns:
        Reordered list of up to top_n ScoredChunk instances.
    """
    if not candidates:
        return []

    if top_n <= 0:
        return []

    if len(candidates) <= 1 or lambda_mult >= 1.0:
        return list(candidates[:top_n])

    remaining = list(candidates)
    selected: list[ScoredChunk] = []

    # Normalize candidate scores stably into [0, 1] range without zeroing out valid candidates
    raw_scores = [c.score for c in remaining]
    max_score = max(raw_scores)
    min_score = min(raw_scores)

    def norm_score(c: ScoredChunk) -> float:
        if 0.0 <= min_score and max_score <= 1.0:
            return c.score
        if max_score > min_score:
            return (c.score - min_score) / (max_score - min_score)
        return 1.0

    # Pick the highest-ranked candidate first
    best_initial = max(remaining, key=lambda c: c.score)
    selected.append(best_initial)
    remaining.remove(best_initial)

    while remaining and len(selected) < top_n:
        best_candidate: ScoredChunk | None = None
        best_mmr_score = -float("inf")

        for cand in remaining:
            rel = norm_score(cand)
            # Find maximum similarity between candidate and any already-selected chunk
            max_sim_to_selected = max(
                _chunk_content_similarity(cand.chunk, sel.chunk) for sel in selected
            )
            mmr_score = (lambda_mult * rel) - ((1.0 - lambda_mult) * max_sim_to_selected)

            if mmr_score > best_mmr_score:
                best_mmr_score = mmr_score
                best_candidate = cand

        if best_candidate is None:
            break

        selected.append(best_candidate)
        remaining.remove(best_candidate)

    return selected
