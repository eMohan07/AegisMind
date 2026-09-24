from __future__ import annotations

import logging
from collections.abc import Sequence

from aegismind_types import Chunk

from aegismind_retrieval.ports import ScoredChunk

logger = logging.getLogger(__name__)

RRF_DEFAULT_K: int = 60


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[ScoredChunk | Chunk]],
    weights: Sequence[float] | None = None,
    k: int = RRF_DEFAULT_K,
) -> list[ScoredChunk]:
    """Combine multiple ranked lists into a single consensus ranking using RRF.

    Formula:
        RRF_score(d) = sum_{m} (w_m / (k + rank_m(d)))

    Args:
        ranked_lists: Sequence of ranked lists (ordered from best to worst).
        weights: Optional weight multiplier for each ranked list.
        k: Smoothing constant parameter, default is 60.

    Returns:
        Sorted list of ScoredChunk instances with RRF scores in descending order.
    """
    if k <= 0:
        msg = f"RRF smoothing parameter k must be positive, got {k}"
        raise ValueError(msg)

    if not ranked_lists:
        return []

    num_lists = len(ranked_lists)
    list_weights = list(weights) if weights is not None else [1.0] * num_lists
    if len(list_weights) != num_lists:
        msg = f"Weights length ({len(list_weights)}) must match ranked_lists length ({num_lists})"
        raise ValueError(msg)

    scores: dict[str, float] = {}
    chunk_map: dict[str, Chunk] = {}

    for ranked_list, weight in zip(ranked_lists, list_weights, strict=True):
        seen_in_list: set[str] = set()
        rank = 1
        for item in ranked_list:
            chunk = item.chunk if isinstance(item, ScoredChunk) else item
            chunk_id = chunk.id

            if chunk_id in seen_in_list:
                continue
            seen_in_list.add(chunk_id)

            chunk_map[chunk_id] = chunk
            reciprocal_score = weight / (k + rank)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + reciprocal_score
            rank += 1

    # Sort descending by score, breaking ties by chunk id for deterministic ordering
    sorted_items = sorted(
        scores.items(),
        key=lambda item: (-item[1], item[0]),
    )

    return [ScoredChunk(chunk=chunk_map[cid], score=score) for cid, score in sorted_items]


def fuse_dense_sparse(
    dense_rankings: Sequence[ScoredChunk | Chunk],
    sparse_rankings: Sequence[ScoredChunk | Chunk],
    k: int = RRF_DEFAULT_K,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> list[ScoredChunk]:
    """Convenience helper to fuse dense semantic and sparse lexical rankings."""
    return reciprocal_rank_fusion(
        ranked_lists=[dense_rankings, sparse_rankings],
        weights=[dense_weight, sparse_weight],
        k=k,
    )
