from __future__ import annotations

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_authz.ports import RelationshipTuple
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.eval.dataset import GOLDEN_EVAL_DATASET
from aegismind_retrieval.eval.harness import RetrievalBenchmarkHarness
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import ACL, Chunk, FeedbackEntry


@pytest.mark.asyncio
async def test_retrieval_eval_harness_benchmark() -> None:
    """Run retrieval benchmark harness against golden dataset verifying Recall and MRR."""
    authz = MemoryAuthzAdapter()
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=64)
    reranker = MockRerankerAdapter()

    # Index sample chunks for Google Drive triples
    gdrive_triples = [t for t in GOLDEN_EVAL_DATASET if t.connector == "google_drive"]
    chunks: list[Chunk] = []
    tuples: list[RelationshipTuple] = []

    for triple in gdrive_triples:
        doc_id = triple.expected_source_doc_ids[0]
        text_content = f"{triple.query}. {triple.expected_answer}"
        embedding = await embedder.embed_query(text_content)
        sparse_emb = await embedder.embed_sparse_query(text_content)

        chunk = Chunk(
            id=f"chunk_{doc_id}",
            document_id=doc_id,
            index=1,
            content=text_content,
            embedding=embedding,
            sparse_embedding=sparse_emb,
            metadata={"title": f"Doc {doc_id}", "tenant_id": "corp-default"},
            acl=ACL(is_public=False),
        )
        chunks.append(chunk)

        tuples.append(
            RelationshipTuple(
                resource=f"document:{doc_id}",
                relation="viewer",
                subject="user:eval_runner",
            )
        )

    await vector_store.upsert(chunks)
    await authz.write_tuples(tuples)

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    harness = RetrievalBenchmarkHarness(pipeline=pipeline)

    # Execute benchmark on google_drive connector
    summary = await harness.run_benchmark(connector_filter="google_drive", top_k=5)

    assert summary.total_queries == len(gdrive_triples)
    assert summary.recall_at_5 >= 0.8
    assert summary.mrr >= 0.5
    assert summary.mean_faithfulness >= 0.5
    assert summary.mean_answer_relevance >= 0.4


def test_triage_negative_feedback_into_dataset() -> None:
    """Verify that thumbs-down feedback items are converted into candidate eval triples."""
    pipeline = RetrievalPipeline(
        authz=MemoryAuthzAdapter(),
        vector_store=MemoryVectorStoreAdapter(),
        embedder=MockEmbedderAdapter(),
        reranker=MockRerankerAdapter(),
    )
    harness = RetrievalBenchmarkHarness(pipeline=pipeline)

    feedbacks = [
        FeedbackEntry(
            id="fb_001",
            query="How to configure Okta SSO?",
            rewritten_query="How to configure Okta SSO in AegisMind?",
            retrieved_chunk_ids=["doc_auth_01_chunk_01"],
            rating="thumbs_down",
            comment="Retrieved Azure AD instead of Okta.",
        ),
        FeedbackEntry(
            id="fb_002",
            query="What is the support SLA?",
            retrieved_chunk_ids=["doc_sla_01_chunk_01"],
            rating="thumbs_up",
        ),
    ]

    triaged = harness.triage_feedback_into_dataset(feedbacks)
    assert len(triaged) == 1
    assert triaged[0].query == "How to configure Okta SSO?"
    assert triaged[0].expected_source_doc_ids == ["doc"]
