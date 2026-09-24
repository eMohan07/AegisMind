from __future__ import annotations

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_ingestion.adapters_parser import MarkdownParserAdapter
from aegismind_ingestion.chunking import SectionAwareChunker
from aegismind_ingestion.pipeline import IngestionPipeline
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import ACL, Principal, Record


@pytest.mark.asyncio
async def test_end_to_end_ingestion_and_retrieval_enforcement() -> None:
    # 1. Setup Shared Infrastructure
    authz = MemoryAuthzAdapter()
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=64)
    reranker = MockRerankerAdapter()

    # 2. Setup Ingestion Pipeline
    ingestion_pipeline = IngestionPipeline(
        parser=MarkdownParserAdapter(),
        vector_store=vector_store,
        embedder=embedder,
        authz=authz,
        chunker=SectionAwareChunker(max_chunk_size=500),
    )

    # 3. Create Sample Raw Records with Different ACLs
    # Record A: Engineering Architecture Spec (allowed: group:engineering)
    rec_eng = Record(
        id="doc_eng_spec",
        source="confluence",
        external_id="conf_101",
        payload={
            "content": (
                "# NextGen Platform Architecture\n"
                "Details on low-latency microservices and Zanzibar authorization."
            ),
            "title": "NextGen Platform Architecture",
            "tenant_id": "tenant_acme",
            "uri": "https://confluence.corp.internal/wiki/doc_eng_spec",
        },
        acl=ACL(allowed_principals=["group:engineering"], is_public=False),
    )

    # Record B: Human Resources Compensation Policy (allowed: group:hr)
    rec_hr = Record(
        id="doc_hr_policy",
        source="workday",
        external_id="wd_202",
        payload={
            "content": (
                "# Compensation and Benefits 2026\n"
                "Details on compensation bands and salary adjustments."
            ),
            "title": "Compensation and Benefits 2026",
            "tenant_id": "tenant_acme",
            "uri": "https://workday.corp.internal/doc_hr_policy",
        },
        acl=ACL(allowed_principals=["group:hr"], is_public=False),
    )

    # Record C: Company Public Handbook (is_public: True)
    rec_public = Record(
        id="doc_public_handbook",
        source="notion",
        external_id="notion_303",
        payload={
            "content": (
                "# Employee General Handbook\n"
                "Mission, core values, and open source collaboration standards."
            ),
            "title": "Employee General Handbook",
            "tenant_id": "tenant_acme",
            "uri": "https://handbook.corp.internal/doc_public_handbook",
        },
        acl=ACL(is_public=True),
    )

    # 4. Ingest Records
    summary = await ingestion_pipeline.ingest_records([rec_eng, rec_hr, rec_public])
    assert summary.records_ingested == 3
    assert summary.documents_created == 3
    assert summary.chunks_indexed >= 3
    assert summary.tuples_written >= 2
    assert len(summary.errors) == 0

    # 5. Setup Retrieval Pipeline
    retrieval_pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    # Scenario 1: Alice (Member of engineering)
    alice = Principal(
        id="alice",
        type="user",
        tenant_id="tenant_acme",
        attributes={"groups": ["engineering"]},
    )
    # Give Alice membership in group:engineering in Zanzibar
    from aegismind_authz.ports import RelationshipTuple

    await authz.write_tuples(
        [
            RelationshipTuple(
                resource="group:engineering",
                relation="member",
                subject="user:alice",
            )
        ]
    )

    res_alice = await retrieval_pipeline.execute(
        query="architecture platform benefits",
        principal=alice,
        top_k=5,
    )

    alice_doc_ids = {r.document_id for r in res_alice.results}
    # Alice can see Engineering Spec and Public Handbook
    assert "doc_eng_spec" in alice_doc_ids
    assert "doc_public_handbook" in alice_doc_ids
    # Alice CANNOT see HR Policy
    assert "doc_hr_policy" not in alice_doc_ids

    # Scenario 2: Bob (Member of HR)
    bob = Principal(
        id="bob",
        type="user",
        tenant_id="tenant_acme",
        attributes={"groups": ["hr"]},
    )
    await authz.write_tuples(
        [
            RelationshipTuple(
                resource="group:hr",
                relation="member",
                subject="user:bob",
            )
        ]
    )

    res_bob = await retrieval_pipeline.execute(
        query="architecture platform compensation benefits",
        principal=bob,
        top_k=5,
    )

    bob_doc_ids = {r.document_id for r in res_bob.results}
    # Bob can see HR Policy and Public Handbook
    assert "doc_hr_policy" in bob_doc_ids
    assert "doc_public_handbook" in bob_doc_ids
    # Bob CANNOT see Engineering Spec
    assert "doc_eng_spec" not in bob_doc_ids

    # Scenario 3: Charlie (Guest with no group memberships)
    charlie = Principal(
        id="charlie",
        type="user",
        tenant_id="tenant_acme",
        attributes={},
    )
    res_charlie = await retrieval_pipeline.execute(
        query="architecture platform compensation handbook",
        principal=charlie,
        top_k=5,
    )

    charlie_doc_ids = {r.document_id for r in res_charlie.results}
    # Charlie CAN ONLY see the public handbook
    assert charlie_doc_ids == {"doc_public_handbook"}
