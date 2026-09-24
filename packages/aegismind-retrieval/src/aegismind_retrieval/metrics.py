from __future__ import annotations

import math
from collections.abc import Sequence


def mean_reciprocal_rank(
    retrieved_rankings: Sequence[Sequence[str]],
    relevant_targets: Sequence[set[str] | list[str]],
) -> float:
    """Compute Mean Reciprocal Rank (MRR) across multiple queries.

    Args:
        retrieved_rankings: List of retrieved item IDs ordered by rank for each query.
        relevant_targets: Target relevant item IDs for each query.

    Returns:
        MRR score between 0.0 and 1.0.
    """
    if not retrieved_rankings or not relevant_targets:
        return 0.0

    reciprocal_ranks = []
    for retrieved, target in zip(retrieved_rankings, relevant_targets, strict=True):
        target_set = set(target)
        rr = 0.0
        for rank, item_id in enumerate(retrieved, start=1):
            if item_id in target_set:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def precision_at_k(
    retrieved: Sequence[str],
    relevant: set[str] | list[str],
    k: int,
) -> float:
    """Compute Precision@k for a single query."""
    if k <= 0:
        return 0.0
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    target_set = set(relevant)
    hits = sum(1 for item in top_k if item in target_set)
    return hits / k


def recall_at_k(
    retrieved: Sequence[str],
    relevant: set[str] | list[str],
    k: int,
) -> float:
    """Compute Recall@k for a single query."""
    target_set = set(relevant)
    if not target_set:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for item in top_k if item in target_set)
    return hits / len(target_set)


def ndcg_at_k(
    retrieved: Sequence[str],
    relevance_scores: dict[str, float],
    k: int,
) -> float:
    """Compute Normalized Discounted Cumulative Gain (NDCG@k).

    Args:
        retrieved: List of retrieved item IDs in ranking order.
        relevance_scores: Mapping from item ID to graded relevance score (e.g. 0 to 3).
        k: Cut-off rank.

    Returns:
        NDCG@k score between 0.0 and 1.0.
    """
    if k <= 0:
        return 0.0

    # 1. DCG@k
    dcg = 0.0
    for idx, item in enumerate(retrieved[:k]):
        rel = relevance_scores.get(item, 0.0)
        # Using standard formula: rel / log2(idx + 2)
        dcg += rel / math.log2(idx + 2)

    # 2. Ideal DCG@k (IDCG)
    ideal_scores = sorted(relevance_scores.values(), reverse=True)[:k]
    idcg = 0.0
    for idx, rel in enumerate(ideal_scores):
        idcg += rel / math.log2(idx + 2)

    if idcg == 0.0:
        return 0.0

    return dcg / idcg
