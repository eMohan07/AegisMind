from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from aegismind_connector_local_filesystem.connector import (
    DEFAULT_SENSITIVE_DENYLIST,
    LocalFilesystemConnector,
    compute_file_hash,
)


@pytest.mark.asyncio
async def test_local_filesystem_connector_reads_files() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        doc1 = tmp_path / "guide.md"
        doc1.write_text(
            "# Sovereign Agent Guide\nThis is a sovereign offline guide.", encoding="utf-8"
        )

        connector = LocalFilesystemConnector(config={"watch_paths": [str(tmp_path)]})
        assert await connector.check() is True

        records = [r async for r in connector.read()]
        assert len(records) == 1
        assert records[0].payload["title"] == "guide.md"
        assert "sovereign offline guide" in records[0].payload["content"].lower()
        assert records[0].source == "local_filesystem"
        assert records[0].payload["content_hash"] == compute_file_hash(doc1)


@pytest.mark.asyncio
async def test_sensitive_path_denylist_enforcement() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Regular file
        safe_file = tmp_path / "notes.txt"
        safe_file.write_text("Public team notes", encoding="utf-8")

        # Sensitive files matching denylist
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET_KEY=supersecret", encoding="utf-8")

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        id_rsa = ssh_dir / "id_rsa"
        id_rsa.write_text("-----BEGIN RSA PRIVATE KEY-----", encoding="utf-8")

        cert = tmp_path / "server.pem"
        cert.write_text("CERTIFICATE DATA", encoding="utf-8")

        connector = LocalFilesystemConnector(
            config={
                "watch_paths": [str(tmp_path)],
                "sensitive_denylist": DEFAULT_SENSITIVE_DENYLIST,
            }
        )

        records = [r async for r in connector.read()]
        indexed_titles = [r.payload["title"] for r in records]

        # Only safe file should be indexed
        assert "notes.txt" in indexed_titles
        assert ".env" not in indexed_titles
        assert "id_rsa" not in indexed_titles
        assert "server.pem" not in indexed_titles


@pytest.mark.asyncio
async def test_content_hashing_skips_unchanged_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        doc = tmp_path / "code.py"
        doc.write_text("print('hello world')", encoding="utf-8")

        connector = LocalFilesystemConnector(config={"watch_paths": [str(tmp_path)]})
        records = [r async for r in connector.read()]
        assert len(records) == 1

        file_hash = records[0].payload["content_hash"]
        canonical_path = records[0].external_id

        # Second read with matching hash in state should skip file
        state = {"content_hashes": {canonical_path: file_hash}}
        second_records = [r async for r in connector.read(state=state)]
        assert len(second_records) == 0

        # Modify file and re-read
        doc.write_text("print('hello sovereign')", encoding="utf-8")
        third_records = [r async for r in connector.read(state=state)]
        assert len(third_records) == 1
        assert "sovereign" in third_records[0].payload["content"]


@pytest.mark.asyncio
async def test_deleted_file_emits_tombstone() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        doc = tmp_path / "delete_me.txt"
        doc.write_text("temporary content", encoding="utf-8")

        connector = LocalFilesystemConnector(config={"watch_paths": [str(tmp_path)]})
        records = [r async for r in connector.read()]
        assert len(records) == 1
        canonical_path = records[0].external_id

        # Delete file
        doc.unlink()

        # Read with previous state
        state = {"content_hashes": {canonical_path: "hash123"}}
        tombstone_records = [r async for r in connector.read(state=state)]
        assert len(tombstone_records) == 1
        assert tombstone_records[0].payload.get("is_tombstone") is True
