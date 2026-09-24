from __future__ import annotations

from typing import Any

import httpx
import pytest
from aegismind_authz.ports import AuthzPort, CheckRequest
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import Chunk, Principal, TokenConsistency

from aegismind_core.app import create_app
from aegismind_core.routes import CoreState


class MockAuthz(AuthzPort):
    def __init__(self, allowed_subjects: set[str] | None = None) -> None:
        self.allowed_subjects = allowed_subjects or {"user:alice", "user:bob"}

    async def bulk_check(
        self,
        requests: list[CheckRequest],
        consistency: TokenConsistency | None = None,
    ) -> list[bool]:
        return [req.subject in self.allowed_subjects for req in requests]

    async def write_tuples(self, tuples: list[Any]) -> TokenConsistency:
        return TokenConsistency(token="zed_mock")

    async def delete_tuples(self, tuples: list[Any]) -> TokenConsistency:
        return TokenConsistency(token="zed_mock")

    async def check_permission(self, subject: Principal, relation: str, resource: str) -> bool:
        return f"{subject.type}:{subject.id}" in self.allowed_subjects


@pytest.fixture
def test_setup() -> tuple[CoreState, RetrievalPipeline]:
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=8)
    reranker = MockRerankerAdapter()
    authz = MockAuthz()

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    state = CoreState(
        retrieval_pipeline=pipeline,
        authz=authz,
        vector_store=vector_store,
    )
    return state, pipeline


@pytest.mark.asyncio
async def test_health_and_probes(test_setup: tuple[CoreState, RetrievalPipeline]) -> None:
    state, _ = test_setup
    app = create_app(state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "service": "aegismind-core"}

        ready_resp = await client.get("/readyz")
        assert ready_resp.status_code == 200
        assert ready_resp.json() == {"status": "ready", "service": "aegismind-core"}

        root_resp = await client.get("/", follow_redirects=False)
        assert root_resp.status_code == 307
        assert root_resp.headers["location"] == "/docs"


@pytest.mark.asyncio
async def test_search_and_audit(test_setup: tuple[CoreState, RetrievalPipeline]) -> None:
    state, _ = test_setup
    app = create_app(state)

    # Populate vector store with sample chunks
    c1 = Chunk(
        id="c1",
        document_id="doc1",
        content="Machine learning pipelines with secure access policies",
        embedding=[0.1] * 8,
        metadata={"title": "ML Security Handbook", "uri": "https://wiki/ml"},
    )
    c2 = Chunk(
        id="c2",
        document_id="doc2",
        content="Confidential financial report Q3",
        embedding=[0.2] * 8,
        metadata={"title": "Q3 Financials", "uri": "https://wiki/fin"},
    )
    await state.vector_store.upsert([c1, c2])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Search as alice (authorized)
        payload = {
            "query": "security policies",
            "principal_id": "alice",
            "principal_type": "user",
            "top_k": 5,
        }
        res = await client.post("/api/v1/search", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert len(data["results"]) > 0
        assert data["results"][0]["document_id"] in ["doc1", "doc2"]
        assert data["results"][0]["citation"] is not None

        # Check audit entry created
        audit_res = await client.get("/api/v1/audit?principal_id=alice")
        assert audit_res.status_code == 200
        audit_data = audit_res.json()
        assert audit_data["total"] >= 1
        assert audit_data["entries"][0]["event_type"] == "search"

        # Search as eve (denied)
        denied_payload = {
            "query": "security policies",
            "principal_id": "eve",
            "principal_type": "user",
            "top_k": 5,
        }
        denied_res = await client.post("/api/v1/search", json=denied_payload)
        assert denied_res.status_code == 200
        assert len(denied_res.json()["results"]) == 0


@pytest.mark.asyncio
async def test_chat_sse_stream(test_setup: tuple[CoreState, RetrievalPipeline]) -> None:
    state, _ = test_setup
    app = create_app(state)

    c1 = Chunk(
        id="c_chat",
        document_id="doc_chat",
        content="AegisMind integrates Zanzibar authorization directly into vector retrieval.",
        embedding=[0.1] * 8,
        metadata={"title": "Architecture Overview"},
    )
    await state.vector_store.upsert([c1])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/chat?query=architecture&principal_id=alice")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        body_text = resp.text
        assert "event: token" in body_text
        assert "event: citation" in body_text
        assert "event: done" in body_text


@pytest.mark.asyncio
async def test_resources_and_group_aliases(test_setup: tuple[CoreState, RetrievalPipeline]) -> None:
    state, _ = test_setup
    state.indexed_resources = [
        {"id": "res_1", "type": "doc", "tenant_id": "t1"},
        {"id": "res_2", "type": "doc", "tenant_id": "t2"},
        {"id": "res_3", "type": "doc", "tenant_id": "t1"},
    ]
    app = create_app(state)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test resources pagination and tenant filter
        all_res = await client.get("/api/v1/resources?limit=2&offset=0")
        assert all_res.status_code == 200
        assert len(all_res.json()["resources"]) == 2
        assert all_res.json()["total"] == 3

        t1_res = await client.get("/api/v1/resources?tenant_id=t1")
        assert t1_res.status_code == 200
        assert t1_res.json()["total"] == 2

        # Test group aliases
        alias_resp = await client.post(
            "/api/v1/group-aliases",
            json={"idp_group": "okta_devs", "canonical_group": "engineering"},
        )
        assert alias_resp.status_code == 200
        assert alias_resp.json()["status"] == "created"

        list_alias_resp = await client.get("/api/v1/group-aliases")
        assert list_alias_resp.status_code == 200
        assert list_alias_resp.json()["aliases"]["okta_devs"] == "engineering"
