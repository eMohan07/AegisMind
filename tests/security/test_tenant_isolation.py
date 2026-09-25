from __future__ import annotations

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_authz.ports import RelationshipTuple
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import ACL, Chunk, Principal


@pytest.mark.guardrail
@pytest.mark.asyncio
async def test_cross_tenant_isolation_with_misconfigured_rebac_tuple() -> None:
    """Verify that cross-tenant queries never return another tenant's data.

    Defense in depth: Even if a Zanzibar relationship tuple is erroneously misconfigured
    to grant a user permissions to an external tenant's document, the retrieval pipeline's
    tenant pre-filter ensures zero leakage.
    """
    authz = MemoryAuthzAdapter()
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=64)
    reranker = MockRerankerAdapter()

    # 1. Tenant Acme confidential chunk
    acme_chunk = Chunk(
        id="chunk_acme_payroll",
        document_id="doc_acme_payroll",
        index=1,
        content="Acme executive payroll and confidential bonus compensation",
        embedding=await embedder.embed_query("payroll and confidential bonus compensation"),
        metadata={
            "title": "Acme Payroll",
            "tenant_id": "tenant_acme",
        },
        acl=ACL(is_public=False),
    )

    # 2. Tenant Beta normal chunk
    beta_chunk = Chunk(
        id="chunk_beta_general",
        document_id="doc_beta_general",
        index=1,
        content="Beta engineering general guidelines and office policy",
        embedding=await embedder.embed_query("engineering general guidelines"),
        metadata={
            "title": "Beta Policy",
            "tenant_id": "tenant_beta",
        },
        acl=ACL(is_public=False),
    )

    await vector_store.upsert([acme_chunk, beta_chunk])

    # 3. Simulate a MISCONFIGURED ReBAC tuple: erroneously granting
    # Mallory (tenant_beta) viewer on Acme's doc!
    await authz.write_tuples(
        [
            RelationshipTuple(
                resource="document:doc_acme_payroll",
                relation="viewer",
                subject="user:mallory",
            ),
            RelationshipTuple(
                resource="document:doc_beta_general",
                relation="viewer",
                subject="user:mallory",
            ),
        ]
    )

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    # Mallory belongs to tenant_beta
    mallory = Principal(id="mallory", type="user", tenant_id="tenant_beta")

    # 4. Mallory queries for payroll data
    res = await pipeline.execute(
        query="payroll and compensation",
        principal=mallory,
        top_k=5,
    )

    # Assert defense in depth: Acme's document MUST NOT be returned
    returned_doc_ids = {r.document_id for r in res.results}
    assert "doc_acme_payroll" not in returned_doc_ids

    for r in res.results:
        assert r.tenant_id == "tenant_beta"
        if r.citation:
            assert r.citation.tenant_id == "tenant_beta"
