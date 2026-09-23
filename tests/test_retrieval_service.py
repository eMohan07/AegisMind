from __future__ import annotations

import pytest

from aegismind_core.domain.models import Chunk, RetrievalQuery
from aegismind_core.domain.permissions import (
    ConsistencyRequirement,
    ConsistencyToken,
    Resource,
    Subject,
)
from aegismind_core.ports.authz import AuthzPort
from aegismind_core.ports.vector_store import VectorStorePort
from aegismind_core.services.retrieval import RetrievalService


@pytest.mark.asyncio
async def test_retrieval_service_dynamic_registry_resolution() -> None:
    # Instantiate service relying entirely on dynamic entry points
    service = RetrievalService()
    assert service._authz is not None
    assert service._vector_store is not None
    assert service._embedder is not None
    assert service._reranker is not None


@pytest.mark.asyncio
async def test_retrieval_service_permissions_enforcement_and_overfetching() -> None:
    service = RetrievalService()
    authz: AuthzPort = service._authz
    vector_store: VectorStorePort = service._vector_store

    # Seed 10 documents into vector store
    # Doc 0 is top similarity but private to Bob
    # Doc 1 is accessible to Alice
    # Doc 2 is accessible to Alice
    # Doc 3..9 are private to Bob
    chunks: list[Chunk] = []
    for i in range(10):
        # We craft embeddings such that doc_0 has highest similarity to query
        chunks.append(
            Chunk(
                id=f"chunk_{i}",
                document_id=f"doc_{i}",
                content=f"Content for knowledge document {i} with machine learning algorithms",
                chunk_index=0,
                embedding=[1.0 - (i * 0.05)] * 16,
            )
        )
    await vector_store.upsert(chunks)

    # Alice only has access to doc_1 and doc_2
    alice = Subject(type="user", id="alice")
    await authz.write_relationship(
        subject=alice,
        relation="reader",
        resource=Resource(type="document", id="doc_1"),
    )
    await authz.write_relationship(
        subject=alice,
        relation="reader",
        resource=Resource(type="document", id="doc_2"),
    )

    # Bob has access to doc_0
    bob = Subject(type="user", id="bob")
    await authz.write_relationship(
        subject=bob,
        relation="reader",
        resource=Resource(type="document", id="doc_0"),
    )

    # Alice queries with top_k=2 and overfetch_factor=4.0
    query = RetrievalQuery(
        query_text="machine learning algorithms",
        user_id="alice",
        top_k=2,
        overfetch_factor=4.0,
        consistency=ConsistencyToken(requirement=ConsistencyRequirement.AT_LEAST_AS_FRESH),
    )

    result = await service.search(query)

    # Evaluated candidates should be min(total, top_k * 4) = 8
    assert result.total_candidates_evaluated == 8
    # Only doc_1 and doc_2 are authorized for Alice among the evaluated candidates
    assert result.authorized_candidates_count == 2
    assert len(result.chunks) == 2

    returned_doc_ids = {c.chunk.document_id for c in result.chunks}
    assert returned_doc_ids == {"doc_1", "doc_2"}

    # Critical security assertion: doc_0 (highest vector similarity) MUST NOT leak to Alice
    assert "doc_0" not in returned_doc_ids

    # Verify Bob querying retrieves doc_0
    bob_query = RetrievalQuery(
        query_text="machine learning algorithms",
        user_id="bob",
        top_k=1,
        overfetch_factor=3.0,
    )
    bob_result = await service.search(bob_query)
    assert len(bob_result.chunks) == 1
    assert bob_result.chunks[0].chunk.document_id == "doc_0"


@pytest.mark.asyncio
async def test_retrieval_service_empty_candidates() -> None:
    service = RetrievalService()
    query = RetrievalQuery(
        query_text="empty space query",
        user_id="nobody",
        top_k=3,
        overfetch_factor=3.0,
    )
    result = await service.search(query)
    assert len(result.chunks) == 0
    assert result.total_candidates_evaluated == 0
    assert result.authorized_candidates_count == 0
