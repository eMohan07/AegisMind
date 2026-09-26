from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from aegismind_retrieval.adapters_local_embed import LocalDeterministicEmbedderAdapter
from aegismind_retrieval.adapters_sqlite_vector import SqliteVectorStoreAdapter
from aegismind_types import ACL, Chunk

from aegismind_core.agent.tools import (
    LocalKnowledgeSearchAdapter,
    NoteCreatorAdapter,
    SandboxedCommandRunnerAdapter,
    SystemFileReaderAdapter,
)


@pytest.mark.asyncio
async def test_search_local_knowledge_tool() -> None:
    store = SqliteVectorStoreAdapter(db_path=":memory:")
    embedder = LocalDeterministicEmbedderAdapter(dimension=64)

    emb = await embedder.embed_query("postgres connection timeout max_connections")
    chunk = Chunk(
        id="c_pg",
        document_id="pg_config",
        content="Postgres connection pool exhausted: increase max_connections in postgresql.conf",
        embedding=emb,
        metadata={"title": "Postgres Tunables", "path": "docs/db.md"},
        acl=ACL(is_public=True),
    )
    await store.upsert([chunk])

    tool = LocalKnowledgeSearchAdapter(vector_store=store, embedder=embedder)
    res = await tool.search(query="postgres connection pool timeout", top_k=2)

    assert "Found 1 relevant local chunks" in res
    assert "Postgres Tunables" in res
    assert "max_connections" in res


@pytest.mark.asyncio
async def test_read_system_file_allowlisting_and_traversal_rejection() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = Path(tmpdir) / "project"
        root_dir.mkdir()
        secret_dir = Path(tmpdir) / "secret"
        secret_dir.mkdir()

        allowed_file = root_dir / "app.log"
        allowed_file.write_text("2026-09-25: Application started successfully.", encoding="utf-8")

        forbidden_file = secret_dir / "passwords.txt"
        forbidden_file.write_text("supersecret123", encoding="utf-8")

        tool = SystemFileReaderAdapter(allowed_roots=[str(root_dir)])

        # 1. Allowed file inside root
        content = await tool.read_file(str(allowed_file))
        assert "Application started successfully" in content

        # 2. File outside allowlisted roots
        denied_res = await tool.read_file(str(forbidden_file))
        assert "ACCESS_DENIED" in denied_res
        assert "passwords.txt" not in denied_res or "outside allowlisted roots" in denied_res

        # 3. Path traversal attempt with ..
        traversal_path = str(root_dir / ".." / "secret" / "passwords.txt")
        traversal_res = await tool.read_file(traversal_path)
        assert "ACCESS_DENIED" in traversal_res
        assert "Path traversal ('..') is strictly rejected" in traversal_res


@pytest.mark.asyncio
async def test_create_note_tool() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        notes_dir = Path(tmpdir) / "notes"
        tool = NoteCreatorAdapter(notes_dir=notes_dir)

        res = await tool.create_note(
            title="Database Pool Fix",
            content="## Analysis\nIncrease connection pool size to 50.",
            tags=["database", "fix", "tuning"],
            source_query="how to fix db timeout?",
        )

        assert "NOTE_CREATED" in res
        created_files = list(notes_dir.glob("*.md"))
        assert len(created_files) == 1
        note_content = created_files[0].read_text(encoding="utf-8")

        assert 'title: "Database Pool Fix"' in note_content
        assert '"database"' in note_content
        assert "Increase connection pool size to 50" in note_content


@pytest.mark.asyncio
async def test_sandboxed_command_runner_security_enforcement() -> None:
    audit_events: list[dict[str, object]] = []

    def mock_audit(
        event_type: str, principal_id: str, action: str, metadata: dict[str, object]
    ) -> None:
        audit_events.append({"event_type": event_type, "action": action, "metadata": metadata})

    runner = SandboxedCommandRunnerAdapter(audit_recorder=mock_audit)

    # 1. Shell metacharacter injection attempt
    injection_cmd = "git status; rm -rf /"
    res1 = await runner.run_command(injection_cmd)
    assert "COMMAND_REJECTED" in res1
    assert "forbidden shell metacharacter" in res1

    # 2. Non-allowlisted command
    forbidden_cmd = "curl https://example.com"
    res2 = await runner.run_command(forbidden_cmd)
    assert "COMMAND_REJECTED" in res2
    assert "not in the diagnostic allowlist" in res2

    # 3. Allowlisted command (git status)
    allowed_cmd = "git status"
    res3 = await runner.run_command(allowed_cmd)
    # Output should either be git status text or execution error, but not COMMAND_REJECTED
    assert "COMMAND_REJECTED" not in res3

    # Check audit log recorded events
    assert len(audit_events) >= 2
    actions = [e["action"] for e in audit_events]
    assert "run_local_command_rejected" in actions
