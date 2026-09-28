from __future__ import annotations

import pytest

from aegismind_core.memory.memory import retrieve_context_v2
from aegismind_core.memory.models import MemoryRecord, MemoryType
from aegismind_core.memory.sqlite_store import SQLiteMemoryStore


@pytest.fixture()
def store(tmp_path: pytest.TempPathFactory) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(db_path=str(tmp_path / "retrieval_injection_test.db"))


class _MockEmbedder:
    async def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]


@pytest.mark.asyncio
async def test_retrieve_context_v2_empty(store: SQLiteMemoryStore) -> None:
    context, used = await retrieve_context_v2(
        store=store,
        query="Hello",
        namespace="global",
        embedder=_MockEmbedder(),
    )
    assert context == ""
    assert used == []


@pytest.mark.asyncio
async def test_retrieve_context_v2_populates_xml(store: SQLiteMemoryStore) -> None:
    # Add an active memory
    mem1 = MemoryRecord(content="User likes dark mode.", namespace="global", type=MemoryType.SEMANTIC)
    saved = await store.add(mem1)
    await store.approve(saved.id)

    # Search (hybrid will find it because of FTS match or just returning active)
    # The _MockEmbedder doesn't matter much for exact match, FTS will hit "dark mode"
    context, used = await retrieve_context_v2(
        store=store,
        query="dark mode",
        namespace="global",
        embedder=_MockEmbedder(),
    )

    # Verify context string formatting
    assert "<memory>" in context
    assert f'<fact id="{saved.id}" type="semantic">' in context
    assert "User likes dark mode." in context
    assert "</memory>" in context

    # Verify memories_used metadata
    assert len(used) == 1
    assert used[0]["id"] == saved.id
    assert used[0]["content"] == "User likes dark mode."


@pytest.mark.asyncio
async def test_retrieve_context_v2_filters_by_namespace(store: SQLiteMemoryStore) -> None:
    mem1 = MemoryRecord(content="Secret workspace project.", namespace="workspace-1", type=MemoryType.EPISODIC)
    saved = await store.add(mem1)
    await store.approve(saved.id)

    # Search in global -> should not find it
    context, used = await retrieve_context_v2(
        store=store,
        query="workspace project",
        namespace="global",
        embedder=_MockEmbedder(),
    )
    assert context == ""
    assert len(used) == 0

    # Search in workspace-1 -> should find it
    context2, used2 = await retrieve_context_v2(
        store=store,
        query="workspace project",
        namespace="workspace-1",
        embedder=_MockEmbedder(),
    )
    assert "Secret workspace project." in context2
    assert len(used2) == 1
