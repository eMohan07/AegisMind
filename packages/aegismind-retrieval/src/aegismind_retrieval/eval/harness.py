from __future__ import annotations

import logging
from collections.abc import Sequence

from aegismind_types import FeedbackEntry, Principal

from aegismind_retrieval.eval.dataset import GOLDEN_EVAL_DATASET, EvalTriple
from aegismind_retrieval.eval.metrics import (
    EvalMetricsSummary,
    aggregate_metrics,
    compute_answer_relevance,
    compute_faithfulness,
    compute_recall_at_k,
    compute_reciprocal_rank,
)
from aegismind_retrieval.pipeline import RetrievalPipeline

logger = logging.getLogger(__name__)


class RetrievalBenchmarkHarness:
    """Benchmark harness executing golden evaluation datasets against RetrievalPipeline."""

    def __init__(self, pipeline: RetrievalPipeline) -> None:
        self.pipeline = pipeline
        self.candidate_eval_triples: list[EvalTriple] = []

    async def run_benchmark(
        self,
        dataset: Sequence[EvalTriple] | None = None,
        connector_filter: str | None = None,
        top_k: int = 5,
    ) -> EvalMetricsSummary:
        """Run evaluation benchmark across dataset triples.

        Args:
            dataset: Sequence of test triples, default is GOLDEN_EVAL_DATASET.
            connector_filter: Optional connector name to filter tests (e.g. google_drive).
            top_k: Top candidate cutoff for evaluation.
        """
        all_triples = list(dataset or GOLDEN_EVAL_DATASET)
        if connector_filter:
            all_triples = [t for t in all_triples if t.connector == connector_filter]

        if not all_triples:
            raise ValueError(f"No evaluation triples found for connector '{connector_filter}'")

        eval_user = Principal(id="eval_runner", type="user", tenant_id="corp-default")

        recalls_1: list[float] = []
        recalls_3: list[float] = []
        recalls_5: list[float] = []
        mrrs: list[float] = []
        faithfulness_scores: list[float] = []
        relevance_scores: list[float] = []

        for triple in all_triples:
            res = await self.pipeline.execute(
                query=triple.query,
                principal=eval_user,
                top_k=top_k,
            )

            retrieved_doc_ids = [r.document_id for r in res.results]
            retrieved_texts = [r.text for r in res.results]

            r1 = compute_recall_at_k(retrieved_doc_ids, triple.expected_source_doc_ids, k=1)
            r3 = compute_recall_at_k(retrieved_doc_ids, triple.expected_source_doc_ids, k=3)
            r5 = compute_recall_at_k(retrieved_doc_ids, triple.expected_source_doc_ids, k=5)
            rr = compute_reciprocal_rank(retrieved_doc_ids, triple.expected_source_doc_ids)

            faithfulness = compute_faithfulness(triple.expected_answer, retrieved_texts)
            relevance = compute_answer_relevance(triple.expected_answer, triple.query)

            recalls_1.append(r1)
            recalls_3.append(r3)
            recalls_5.append(r5)
            mrrs.append(rr)
            faithfulness_scores.append(faithfulness)
            relevance_scores.append(relevance)

        summary = aggregate_metrics(
            query_recalls_1=recalls_1,
            query_recalls_3=recalls_3,
            query_recalls_5=recalls_5,
            query_mrrs=mrrs,
            query_faithfulness=faithfulness_scores,
            query_relevance=relevance_scores,
        )

        logger.info(
            "Benchmark completed for %d queries: R@1=%.4f, R@5=%.4f, MRR=%.4f, Faithfulness=%.4f",
            summary.total_queries,
            summary.recall_at_1,
            summary.recall_at_5,
            summary.mrr,
            summary.mean_faithfulness,
        )
        return summary

    def triage_feedback_into_dataset(
        self,
        feedback_entries: list[FeedbackEntry],
    ) -> list[EvalTriple]:
        """Convert negative user feedback entries into new candidate evaluation test cases."""
        new_triples: list[EvalTriple] = []
        for idx, fb in enumerate(feedback_entries):
            if fb.rating == "thumbs_down":
                triple = EvalTriple(
                    id=f"triage_fb_{fb.id}_{idx}",
                    connector="user_feedback",
                    query=fb.query,
                    expected_answer=fb.comment or "User flagged answer as unsatisfactory",
                    expected_source_doc_ids=[cid.split("_")[0] for cid in fb.retrieved_chunk_ids],
                    metadata={"rewritten_query": fb.rewritten_query or ""},
                )
                new_triples.append(triple)
                self.candidate_eval_triples.append(triple)

        logger.info(
            "Triaged %d negative feedback items into candidate eval cases", len(new_triples)
        )
        return new_triples
