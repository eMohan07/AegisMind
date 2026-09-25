from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field


class EvalMetricsSummary(BaseModel):
    """Aggregate benchmark metrics summary."""

    model_config = ConfigDict(frozen=True)

    total_queries: int = Field(..., description="Total test queries evaluated")
    recall_at_1: float = Field(..., description="Mean Recall at top 1")
    recall_at_3: float = Field(..., description="Mean Recall at top 3")
    recall_at_5: float = Field(..., description="Mean Recall at top 5")
    mrr: float = Field(..., description="Mean Reciprocal Rank across all queries")
    mean_faithfulness: float = Field(
        ...,
        description="Factual consistency score between answer and retrieved chunks",
    )
    mean_answer_relevance: float = Field(
        ...,
        description="Semantic alignment score between question and generated answer",
    )


def compute_recall_at_k(
    retrieved_doc_ids: Sequence[str],
    expected_doc_ids: Sequence[str],
    k: int,
) -> float:
    """Compute Recall@k for a single query."""
    if not expected_doc_ids:
        return 0.0
    cutoff = retrieved_doc_ids[:k]
    matched = any(exp in cutoff for exp in expected_doc_ids)
    return 1.0 if matched else 0.0


def compute_reciprocal_rank(
    retrieved_doc_ids: Sequence[str],
    expected_doc_ids: Sequence[str],
) -> float:
    """Compute Reciprocal Rank (1 / rank) of the first relevant document."""
    exp_set = set(expected_doc_ids)
    for rank, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in exp_set:
            return 1.0 / rank
    return 0.0


def compute_faithfulness(
    generated_answer: str,
    retrieved_contexts: Sequence[str],
) -> float:
    """Compute lightweight faithfulness score measuring ground-truth factual support.

    Computes token claim overlap between the generated answer sentences and verified
    retrieved context chunks.
    """
    if not generated_answer or not retrieved_contexts:
        return 0.0

    answer_words = [
        w.strip(".,!?:;\"'()[]{}").lower() for w in generated_answer.split() if len(w) > 3
    ]
    if not answer_words:
        return 1.0

    context_text = " ".join(retrieved_contexts).lower()
    supported_words = sum(1 for w in answer_words if w in context_text)
    return round(supported_words / len(answer_words), 4)


STOP_WORDS: set[str] = {
    "what",
    "is",
    "the",
    "are",
    "how",
    "do",
    "where",
    "for",
    "with",
    "and",
    "or",
    "can",
    "who",
    "when",
    "why",
    "which",
    "about",
    "from",
    "into",
    "onto",
    "that",
    "this",
    "these",
    "those",
    "have",
    "has",
    "had",
    "will",
    "would",
    "should",
}


def compute_answer_relevance(
    generated_answer: str,
    user_query: str,
) -> float:
    """Compute answer relevance score measuring topical query-answer alignment."""
    if not generated_answer or not user_query:
        return 0.0

    raw_query_words = [w.strip(".,!?:;\"'()[]{}").lower() for w in user_query.split()]
    query_keywords = [w for w in raw_query_words if len(w) > 2 and w not in STOP_WORDS]
    if not query_keywords:
        query_keywords = [w for w in raw_query_words if len(w) > 2]
    if not query_keywords:
        return 1.0

    ans_words = [w.strip(".,!?:;\"'()[]{}").lower() for w in generated_answer.split() if len(w) > 2]
    if not ans_words:
        return 0.0

    # Match topical keywords via root prefix or substring matching
    matched = 0
    for qw in query_keywords:
        stem = qw[:4] if len(qw) >= 4 else qw
        if any(stem in aw or aw.startswith(stem) for aw in ans_words):
            matched += 1

    return round(matched / len(query_keywords), 4)


def aggregate_metrics(
    query_recalls_1: list[float],
    query_recalls_3: list[float],
    query_recalls_5: list[float],
    query_mrrs: list[float],
    query_faithfulness: list[float],
    query_relevance: list[float],
) -> EvalMetricsSummary:
    """Aggregate per-query benchmark results into a final summary report."""
    n = max(1, len(query_mrrs))
    return EvalMetricsSummary(
        total_queries=len(query_mrrs),
        recall_at_1=round(sum(query_recalls_1) / n, 4),
        recall_at_3=round(sum(query_recalls_3) / n, 4),
        recall_at_5=round(sum(query_recalls_5) / n, 4),
        mrr=round(sum(query_mrrs) / n, 4),
        mean_faithfulness=round(sum(query_faithfulness) / n, 4),
        mean_answer_relevance=round(sum(query_relevance) / n, 4),
    )
