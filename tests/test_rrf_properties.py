from __future__ import annotations

import pytest
from aegismind_retrieval.rrf import RRF_DEFAULT_K, fuse_dense_sparse, reciprocal_rank_fusion
from aegismind_types import Chunk


def _make_chunk(chunk_id: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=f"doc_{chunk_id}",
        content=f"Content for chunk {chunk_id}",
    )


def test_rrf_default_constant_calculation() -> None:
    c1 = _make_chunk("c1")
    c2 = _make_chunk("c2")

    results = reciprocal_rank_fusion(ranked_lists=[[c1, c2]], k=60)
    assert len(results) == 2

    # Rank 1: 1 / (60 + 1) = 1 / 61
    expected_c1 = 1.0 / 61.0
    # Rank 2: 1 / (60 + 2) = 1 / 62
    expected_c2 = 1.0 / 62.0

    assert pytest.approx(results[0].score, rel=1e-5) == expected_c1
    assert pytest.approx(results[1].score, rel=1e-5) == expected_c2
    assert results[0].chunk.id == "c1"
    assert results[1].chunk.id == "c2"


def test_rrf_monotonicity() -> None:
    # If chunk A is ranked higher than chunk B in both lists, score(A) must be > score(B)
    cA = _make_chunk("cA")
    cB = _make_chunk("cB")
    cC = _make_chunk("cC")

    list1 = [cA, cB, cC]
    list2 = [cA, cB, cC]

    fused = reciprocal_rank_fusion(ranked_lists=[list1, list2], k=RRF_DEFAULT_K)
    scores = {item.chunk.id: item.score for item in fused}

    assert scores["cA"] > scores["cB"] > scores["cC"]


def test_rrf_symmetry() -> None:
    # Item 1 is (rank 1 in L1, rank 2 in L2)
    # Item 2 is (rank 2 in L1, rank 1 in L2)
    # With equal weights, Item 1 and Item 2 must have identical scores
    c1 = _make_chunk("c1")
    c2 = _make_chunk("c2")

    list1 = [c1, c2]
    list2 = [c2, c1]

    fused = fuse_dense_sparse(dense_rankings=list1, sparse_rankings=list2, k=60)
    scores = {item.chunk.id: item.score for item in fused}

    assert pytest.approx(scores["c1"], rel=1e-6) == scores["c2"]


def test_rrf_disjoint_lists() -> None:
    # c_dense appears only in dense, c_sparse only in sparse, c_both in both
    c_dense = _make_chunk("c_dense")
    c_sparse = _make_chunk("c_sparse")
    c_both = _make_chunk("c_both")

    dense_list = [c_both, c_dense]
    sparse_list = [c_both, c_sparse]

    fused = fuse_dense_sparse(dense_list, sparse_list, k=60)
    assert fused[0].chunk.id == "c_both"

    score_both = fused[0].score
    score_dense = next(item.score for item in fused if item.chunk.id == "c_dense")
    score_sparse = next(item.score for item in fused if item.chunk.id == "c_sparse")

    # c_both gets (1/61 + 1/61), while c_dense and c_sparse get (1/62) each
    assert score_both > score_dense
    assert score_both > score_sparse
    assert pytest.approx(score_dense, rel=1e-6) == score_sparse


def test_rrf_weighted_fusion() -> None:
    c1 = _make_chunk("c1")
    c2 = _make_chunk("c2")

    # Dense weight = 2.0, Sparse weight = 1.0
    dense_list = [c1, c2]
    sparse_list = [c2, c1]

    fused = reciprocal_rank_fusion(
        ranked_lists=[dense_list, sparse_list],
        weights=[2.0, 1.0],
        k=60,
    )

    # c1: 2.0/61 + 1.0/62
    # c2: 2.0/62 + 1.0/61
    score_c1 = next(item.score for item in fused if item.chunk.id == "c1")
    score_c2 = next(item.score for item in fused if item.chunk.id == "c2")

    assert score_c1 > score_c2


def test_rrf_validation_errors() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        reciprocal_rank_fusion(ranked_lists=[[]], k=0)

    with pytest.raises(ValueError, match="Weights length"):
        reciprocal_rank_fusion(ranked_lists=[[], []], weights=[1.0])


def test_rrf_empty_inputs() -> None:
    assert reciprocal_rank_fusion(ranked_lists=[]) == []
    assert reciprocal_rank_fusion(ranked_lists=[[], []]) == []
