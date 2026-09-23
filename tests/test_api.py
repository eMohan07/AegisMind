from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aegismind_api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "AegisMind"}


def test_api_workflow(client: TestClient) -> None:
    # 1. Ingest documents
    doc1 = client.post(
        "/api/v1/documents",
        json={
            "document_id": "api_doc_secret",
            "content": "Super secret financial quarterly earnings report",
        },
    )
    assert doc1.status_code == 200

    doc2 = client.post(
        "/api/v1/documents",
        json={
            "document_id": "api_doc_public",
            "content": "Public guidelines and company mission statement",
        },
    )
    assert doc2.status_code == 200

    # 2. Grant Alice access to secret document
    rel = client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "user",
            "subject_id": "alice_api",
            "relation": "reader",
            "resource_type": "document",
            "resource_id": "api_doc_secret",
        },
    )
    assert rel.status_code == 200
    assert "zed_token" in rel.json()

    # Grant wildcard access to public document
    rel_pub = client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "user",
            "subject_id": "*",
            "relation": "reader",
            "resource_type": "document",
            "resource_id": "api_doc_public",
        },
    )
    assert rel_pub.status_code == 200

    # 3. Alice searches: should see both secret and public docs
    search_alice = client.post(
        "/api/v1/search",
        json={
            "query_text": "financial guidelines",
            "user_id": "alice_api",
            "top_k": 5,
            "overfetch_factor": 3.0,
        },
    )
    assert search_alice.status_code == 200
    alice_data = search_alice.json()
    alice_docs = {c["chunk"]["document_id"] for c in alice_data["chunks"]}
    assert "api_doc_secret" in alice_docs

    # 4. Bob searches: should NOT see secret doc, only public doc
    search_bob = client.post(
        "/api/v1/search",
        json={
            "query_text": "financial guidelines",
            "user_id": "bob_api",
            "top_k": 5,
            "overfetch_factor": 3.0,
        },
    )
    assert search_bob.status_code == 200
    bob_data = search_bob.json()
    bob_docs = {c["chunk"]["document_id"] for c in bob_data["chunks"]}
    assert "api_doc_secret" not in bob_docs
    assert "api_doc_public" in bob_docs
