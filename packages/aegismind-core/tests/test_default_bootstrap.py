from __future__ import annotations

import httpx
import pytest

from aegismind_core.app import create_app


@pytest.mark.asyncio
async def test_default_app_bootstrap_and_chat_synthesis() -> None:
    """Verify that create_app bootstraps default state and answers questions correctly."""
    app = create_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test search with user_id alias
        search_resp = await client.post(
            "/api/v1/search",
            json={"query": "zero stale read revocation", "user_id": "alice"},
        )
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert len(search_data["results"]) > 0
        titles = [r["title"] for r in search_data["results"]]
        assert any("SEC-892" in t for t in titles)

        # 2. Test chat SSE stream with alice
        chat_resp = await client.get(
            "/api/v1/chat?query=How+does+zero+stale+read+revocation+work%3F&user_id=alice"
        )
        assert chat_resp.status_code == 200
        assert "text/event-stream" in chat_resp.headers["content-type"]
        body = chat_resp.text
        assert "event: token" in body
        assert "event: citations" in body
        assert "event: done" in body
        assert "SEC-892" in body or "Zanzibar" in body or "revocation" in body

        # 3. Test connectors list returns discovered connectors
        conn_resp = await client.get("/api/v1/connectors")
        assert conn_resp.status_code == 200
        conn_data = conn_resp.json()
        assert "connectors" in conn_data
        assert len(conn_data["connectors"]) > 0
