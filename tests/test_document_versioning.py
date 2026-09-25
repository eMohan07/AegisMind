from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_ingestion.adapters_parser import TextParserAdapter
from aegismind_ingestion.chunking import SectionAwareChunker
from aegismind_ingestion.pipeline import IngestionPipeline
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import ACL, Principal, Record


@pytest.fixture
def versioning_fixture() -> dict[str, Any]:
    vector_store = MemoryVectorStoreAdapter()
    authz = MemoryAuthzAdapter()
    embedder = MockEmbedderAdapter(dimension=32)
    reranker = MockRerankerAdapter()
    parser = TextParserAdapter()
    chunker = SectionAwareChunker(max_chunk_size=120, chunk_overlap=0)

    ingestion = IngestionPipeline(
        parser=parser,
        vector_store=vector_store,
        embedder=embedder,
        authz=authz,
        chunker=chunker,
    )
    retrieval = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )
    return {
        "vector_store": vector_store,
        "authz": authz,
        "embedder": embedder,
        "ingestion": ingestion,
        "retrieval": retrieval,
    }


@pytest.mark.asyncio
async def test_document_versioning_and_embedding_reuse(versioning_fixture: dict[str, Any]) -> None:
    ingestion: IngestionPipeline = versioning_fixture["ingestion"]
    vector_store: MemoryVectorStoreAdapter = versioning_fixture["vector_store"]
    embedder: MockEmbedderAdapter = versioning_fixture["embedder"]
    retrieval: RetrievalPipeline = versioning_fixture["retrieval"]

    # 1. Ingest initial document v1 with two distinct paragraphs
    rec_v1 = Record(
        id="doc_alpha",
        source="wiki",
        external_id="ext_doc_alpha",
        payload={
            "id": "doc_alpha",
            "title": "Alpha Architecture Document",
            "content": (
                "# Section A\nThe fundamental kernel is immutable and deterministic.\n\n"
                "# Section B\nInitial draft outlining temporary caching strategies."
            ),
        },
        acl=ACL(allowed_principals=["alice"]),
    )

    summary_v1 = await ingestion.ingest_records([rec_v1])
    assert summary_v1.chunks_indexed >= 2

    # Verify v1 chunks in vector store
    v1_chunks = await vector_store.get_by_document("doc_alpha")
    assert len(v1_chunks) >= 2
    assert all(c.version == 1 for c in v1_chunks)
    assert all(not c.is_deleted for c in v1_chunks)

    # Track Chunk A content hash and vector
    chunk_a_v1 = next(c for c in v1_chunks if "Section A" in c.content)
    assert chunk_a_v1.content_hash is not None
    assert chunk_a_v1.embedding is not None
    orig_embedding = list(chunk_a_v1.embedding)
    orig_hash = chunk_a_v1.content_hash

    # Spy on embedder.embed_documents
    embed_mock = AsyncMock(wraps=embedder.embed_documents)
    embedder.embed_documents = embed_mock  # type: ignore[method-assign]

    # 2. Re-ingest document v2 with Section A UNCHANGED, Section B MODIFIED
    rec_v2 = Record(
        id="doc_alpha",
        source="wiki",
        external_id="ext_doc_alpha",
        payload={
            "id": "doc_alpha",
            "title": "Alpha Architecture Document",
            "content": (
                "# Section A\nThe fundamental kernel is immutable and deterministic.\n\n"
                "# Section B\nRevised production policy replacing all "
                "temporary caches with WORM storage."
            ),
        },
        acl=ACL(allowed_principals=["alice"]),
    )

    summary_v2 = await ingestion.ingest_records([rec_v2])
    assert summary_v2.chunks_indexed >= 2

    # Verify that unchanged Section A did not need re-embedding
    # embed_documents should only be called for the 1 modified chunk (Section B)
    total_reembedded = sum(len(args[0][0]) for args in embed_mock.call_args_list)
    assert total_reembedded == 1
    assert "Revised production policy" in embed_mock.call_args_list[0][0][0][0]

    # Verify v2 active chunks
    active_chunks = await vector_store.get_by_document("doc_alpha")
    assert len(active_chunks) >= 2
    assert all(c.version == 2 for c in active_chunks)
    assert all(not c.is_deleted for c in active_chunks)

    # Verify Chunk A in v2 preserved identical embedding and hash
    chunk_a_v2 = next(c for c in active_chunks if "Section A" in c.content)
    assert chunk_a_v2.content_hash == orig_hash
    assert chunk_a_v2.embedding == orig_embedding

    # 3. Verify retrieval excludes tombstones and returns latest version
    principal = Principal(id="alice", type="user", tenant_id="corp-default")
    search_res = await retrieval.execute(
        query="temporary caching strategies",
        principal=principal,
        top_k=5,
    )
    # The old section B text should NOT be present in active search results
    for r in search_res.results:
        assert "Initial draft outlining temporary caching strategies" not in r.text

    # 4. Verify tombstoned v1 chunks exist in storage with is_deleted=True
    all_stored_chunks = list(vector_store._chunks.values())
    tombstones = [c for c in all_stored_chunks if c.document_id == "doc_alpha" and c.is_deleted]
    assert len(tombstones) >= 2
    assert all(c.deleted_at is not None for c in tombstones)

    # 5. Vacuum tombstones
    vacuumed_count = await vector_store.vacuum_tombstones(older_than_seconds=0)
    assert vacuumed_count >= 2
    remaining_stored = [c for c in vector_store._chunks.values() if c.document_id == "doc_alpha"]
    assert all(not c.is_deleted for c in remaining_stored)
