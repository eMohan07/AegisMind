from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from aegismind_retrieval.adapters_local_embed import (
    LocalDeterministicEmbedderAdapter,
)
from aegismind_retrieval.adapters_sqlite_vector import SqliteVectorStoreAdapter
from aegismind_types import ACL, Chunk


@pytest.mark.asyncio
async def test_deterministic_local_embedder() -> None:
    embedder = LocalDeterministicEmbedderAdapter(dimension=128)
    q_emb = await embedder.embed_query("sovereign agent architecture")
    assert len(q_emb) == 128
    assert isinstance(q_emb[0], float)

    docs = ["Doc 1 content", "Doc 2 content"]
    doc_embs = await embedder.embed_documents(docs)
    assert len(doc_embs) == 2
    assert len(doc_embs[0]) == 128


@pytest.mark.asyncio
async def test_sqlite_vector_store_crud_and_query() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "vectors.db"
        store = SqliteVectorStoreAdapter(db_path=db_path)

        embedder = LocalDeterministicEmbedderAdapter(dimension=64)
        emb1 = await embedder.embed_query("database connection error timeout")
        emb2 = await embedder.embed_query("frontend react rendering vite")

        chunk1 = Chunk(
            id="c1",
            document_id="doc_db",
            content="Error 500: Database connection pool exhausted timeout",
            embedding=emb1,
            metadata={"source": "logs", "tenant_id": "local"},
            acl=ACL(is_public=True),
        )
        chunk2 = Chunk(
            id="c2",
            document_id="doc_ui",
            content="React components render successfully with Vite",
            embedding=emb2,
            metadata={"source": "docs", "tenant_id": "local"},
            acl=ACL(is_public=True),
        )

        await store.upsert([chunk1, chunk2])

        # Query for database errors
        results = await store.query_dense(emb1, top_k=2)
        assert len(results) == 2
        assert results[0].chunk.id == "c1"
        assert "Database connection pool" in results[0].chunk.content
        assert results[0].score > 0.8

        # Test soft delete
        deleted_count = await store.soft_delete_document("doc_db")
        assert deleted_count == 1

        # Query should no longer return c1
        results_after_delete = await store.query_dense(emb1, top_k=2)
        assert len(results_after_delete) == 1
        assert results_after_delete[0].chunk.id == "c2"

        # Vacuum tombstones
        vacuumed = await store.vacuum_tombstones(older_than_seconds=0)
        assert vacuumed == 1
