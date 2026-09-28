from __future__ import annotations

import pytest
from aegismind_core.memory.models import MemoryRecord, MemoryType
from fastapi.testclient import TestClient

from aegismind_core.bootstrap import init_default_core_state
from aegismind_core.routes import create_routes


@pytest.fixture
async def app_client(tmp_path: pytest.TempPathFactory) -> TestClient:
    """Fixture that builds a FastAPI client with an isolated SQLiteMemoryStore."""
    from aegismind_core.memory.sqlite_store import SQLiteMemoryStore
    from fastapi import FastAPI

    state = await init_default_core_state()
    # Replace long term memory with a fresh isolated DB
    state.long_term_memory = SQLiteMemoryStore(db_path=str(tmp_path / "api_test.db"))

    # Pre-seed some data
    rec1 = MemoryRecord(content="Alice likes Python.", namespace="global", type=MemoryType.SEMANTIC)
    rec2 = MemoryRecord(
        content="Alice works from home.", namespace="global", type=MemoryType.EPISODIC
    )

    s1 = await state.long_term_memory.add(rec1)
    s2 = await state.long_term_memory.add(rec2)  # noqa: F841

    await state.long_term_memory.approve(s1.id)
    # s2 remains PENDING

    app = FastAPI()
    app.include_router(create_routes(state))
    return TestClient(app)


@pytest.mark.asyncio
async def test_api_list_memory_records(app_client: TestClient) -> None:
    res = app_client.get("/api/v1/memory/records?namespace=global")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2

    # Filter by status
    res = app_client.get("/api/v1/memory/records?status=active")
    data = res.json()
    assert len(data) == 1
    assert data[0]["content"] == "Alice likes Python."

    # Filter by type
    res = app_client.get("/api/v1/memory/records?type=episodic")
    data = res.json()
    assert len(data) == 1
    assert data[0]["content"] == "Alice works from home."


@pytest.mark.asyncio
async def test_api_get_memory_record(app_client: TestClient) -> None:
    # First get list to find ID
    res = app_client.get("/api/v1/memory/records?status=active")
    mem_id = res.json()[0]["id"]

    res = app_client.get(f"/api/v1/memory/records/{mem_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == mem_id
    assert data["content"] == "Alice likes Python."


@pytest.mark.asyncio
async def test_api_get_memory_record_not_found(app_client: TestClient) -> None:
    res = app_client.get("/api/v1/memory/records/mem_doesnotexist")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_api_update_memory_record(app_client: TestClient) -> None:
    res = app_client.get("/api/v1/memory/records?status=active")
    mem_id = res.json()[0]["id"]

    patch_res = app_client.patch(
        f"/api/v1/memory/records/{mem_id}",
        json={"content": "Alice strongly prefers Python.", "importance": 0.9},
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["content"] == "Alice strongly prefers Python."
    assert data["importance"] == 0.9


@pytest.mark.asyncio
async def test_api_approve_memory_record(app_client: TestClient) -> None:
    # Find pending
    res = app_client.get("/api/v1/memory/records?status=pending")
    mem_id = res.json()[0]["id"]

    patch_res = app_client.patch(f"/api/v1/memory/records/{mem_id}", json={"status": "active"})
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "active"

    # Verify audit event was created
    audit_res = app_client.get(f"/api/v1/memory/records/{mem_id}/audit")
    assert audit_res.status_code == 200
    events = audit_res.json()
    assert any(e["event"] == "approved" for e in events)


@pytest.mark.asyncio
async def test_api_delete_memory_record(app_client: TestClient) -> None:
    res = app_client.get("/api/v1/memory/records?status=active")
    mem_id = res.json()[0]["id"]

    del_res = app_client.delete(f"/api/v1/memory/records/{mem_id}")
    assert del_res.status_code == 200

    # Should now be forgotten
    get_res = app_client.get(f"/api/v1/memory/records/{mem_id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "forgotten"
