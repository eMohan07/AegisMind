from __future__ import annotations

import pytest
from aegismind_retrieval.metrics import (
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


def test_mean_reciprocal_rank() -> None:
    # Query 1: relevant item at rank 1 -> RR = 1.0
    # Query 2: relevant item at rank 2 -> RR = 0.5
    # Query 3: relevant item not found -> RR = 0.0
    # MRR = (1.0 + 0.5 + 0.0) / 3 = 0.5
    retrieved = [
        ["doc_1", "doc_2", "doc_3"],
        ["doc_4", "doc_5", "doc_6"],
        ["doc_7", "doc_8", "doc_9"],
    ]
    targets = [
        {"doc_1"},
        {"doc_5"},
        {"doc_10"},
    ]

    mrr = mean_reciprocal_rank(retrieved, targets)
    assert pytest.approx(mrr, rel=1e-5) == 0.5


def test_precision_at_k() -> None:
    retrieved = ["doc_1", "doc_2", "doc_3", "doc_4", "doc_5"]
    relevant = {"doc_1", "doc_3", "doc_9"}

    # At k=3: doc_1 and doc_3 are relevant (2/3)
    p3 = precision_at_k(retrieved, relevant, k=3)
    assert pytest.approx(p3, rel=1e-5) == 2.0 / 3.0

    # At k=5: 2 relevant in top 5 (2/5 = 0.4)
    p5 = precision_at_k(retrieved, relevant, k=5)
    assert pytest.approx(p5, rel=1e-5) == 0.4


def test_recall_at_k() -> None:
    retrieved = ["doc_1", "doc_2", "doc_3"]
    relevant = {"doc_1", "doc_3", "doc_4", "doc_5"}  # 4 total relevant items

    # At k=3: retrieved doc_1 and doc_3 out of 4 total -> 2/4 = 0.5
    r3 = recall_at_k(retrieved, relevant, k=3)
    assert pytest.approx(r3, rel=1e-5) == 0.5


def test_ndcg_at_k_perfect_ranking() -> None:
    # Perfect ranking should yield NDCG = 1.0
    retrieved = ["doc_1", "doc_2", "doc_3"]
    relevance = {"doc_1": 3.0, "doc_2": 2.0, "doc_3": 1.0}

    score = ndcg_at_k(retrieved, relevance, k=3)
    assert pytest.approx(score, rel=1e-5) == 1.0


def test_ndcg_at_k_suboptimal_ranking() -> None:
    # Inverted ranking should yield NDCG < 1.0
    retrieved = ["doc_3", "doc_2", "doc_1"]
    relevance = {"doc_1": 3.0, "doc_2": 2.0, "doc_3": 1.0}

    score = ndcg_at_k(retrieved, relevance, k=3)
    assert 0.0 < score < 1.0
