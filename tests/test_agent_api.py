from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from aegismind_core.app import create_app
from aegismind_core.routes import CoreState


def test_notes_api_endpoints() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_dir = Path(tmpdir) / "notes"
        notes_dir.mkdir()

        # Create test note
        test_note = notes_dir / "20260925_db_fix.md"
        test_note.write_text(
            '---\ntitle: "Database Fix"\ntags: ["db", "remediation"]\n'
            'created_at: "2026-09-25T12:00:00Z"\n---\n\nIncrease pool size.',
            encoding="utf-8",
        )

        app = create_app(state=CoreState())
        client = TestClient(app)

        # 1. List notes
        res = client.get(f"/api/v1/notes?notes_dir={notes_dir}")
        assert res.status_code == 200
        notes = res.json()
        assert len(notes) == 1
        assert notes[0]["title"] == "Database Fix"
        assert "db" in notes[0]["tags"]
        assert "Increase pool size" in notes[0]["preview"]

        # 2. Get note detail
        detail_res = client.get(f"/api/v1/notes/20260925_db_fix.md?notes_dir={notes_dir}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["title"] == "Database Fix"
        assert "Increase pool size" in detail["content"]

        # 3. List agent tools audit feed
        tools_res = client.get("/api/v1/agent/tools")
        assert tools_res.status_code == 200
        assert isinstance(tools_res.json(), list)
