from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from aegismind_retrieval.adapters_local_embed import LocalDeterministicEmbedderAdapter
from aegismind_retrieval.adapters_sqlite_vector import SqliteVectorStoreAdapter
from aegismind_types import ACL, Chunk

from aegismind_core.agent.loop import AgentRunResult, SovereignAgentLoop
from aegismind_core.agent.tools import (
    LocalKnowledgeSearchAdapter,
    NoteCreatorAdapter,
    SandboxedCommandRunnerAdapter,
    SystemFileReaderAdapter,
)


@pytest.mark.asyncio
async def test_fetch_and_note_end_to_end_workflow() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        logs_dir = tmp_path / "logs"
        notes_dir = tmp_path / "storage" / "notes"
        docs_dir = tmp_path / "docs"

        logs_dir.mkdir(parents=True)
        notes_dir.mkdir(parents=True)
        docs_dir.mkdir(parents=True)

        # 1. Create fixture error log file
        log_file = logs_dir / "app.err.log"
        log_file.write_text(
            "2026-09-25T21:04:12 ERROR [db_pool] Connection pool exhausted (max=10). "
            "Client request timed out waiting for available connection after 5000ms.\n"
            "Traceback: psycopg.OperationalError: server connection pool limit reached",
            encoding="utf-8",
        )

        # 2. Seed fixture indexed docs in the local vector store
        vector_store = SqliteVectorStoreAdapter(db_path=":memory:")
        embedder = LocalDeterministicEmbedderAdapter(dimension=64)

        doc_content = (
            "Runbook: Database Connection Pool Sizing and Timeout Tuning\n"
            "When encountering 'Connection pool exhausted (max=10)', increase DB_POOL_MAX to 50 "
            "in production and configure DB_POOL_TIMEOUT=30s in config/database.yaml."
        )
        emb = await embedder.embed_query("Connection pool exhausted database timeout")
        chunk = Chunk(
            id="runbook_chunk_01",
            document_id="runbook_db",
            content=doc_content,
            embedding=emb,
            metadata={"title": "DB Pool Sizing Runbook", "path": str(docs_dir / "db_runbook.md")},
            acl=ACL(is_public=True),
        )
        await vector_store.upsert([chunk])

        # 3. Initialize sandboxed tools
        search_tool = LocalKnowledgeSearchAdapter(vector_store=vector_store, embedder=embedder)
        file_tool = SystemFileReaderAdapter(allowed_roots=[str(tmp_path)])
        note_tool = NoteCreatorAdapter(notes_dir=notes_dir)
        command_tool = SandboxedCommandRunnerAdapter(working_dir=tmp_path)

        # 4. Realistic simulated Ollama model conforming to qwen2.5/llama3.2 tool calling protocol
        simulated_step = 0

        async def simulated_ollama_chat(
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]],
        ) -> dict[str, Any]:
            nonlocal simulated_step
            simulated_step += 1

            if simulated_step == 1:
                # Step 1: Model inspects error logs
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "read_system_file",
                                "arguments": {"path": str(log_file)},
                            }
                        }
                    ],
                }
            elif simulated_step == 2:
                # Step 2: Model noticed pool exhausted in logs, searches local knowledge base
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_local_knowledge",
                                "arguments": {
                                    "query": "Connection pool exhausted database timeout",
                                    "top_k": 3,
                                },
                            }
                        }
                    ],
                }
            elif simulated_step == 3:
                # Step 3: Model found runbook fix, creates note
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "create_note",
                                "arguments": {
                                    "title": "Database Connection Pool Fix",
                                    "content": (
                                        "## Issue Diagnosis\n"
                                        "The application failed because connection pool (max=10) "
                                        "was exhausted.\n\n"
                                        "## Remediation\n"
                                        "Increase DB_POOL_MAX to 50 and set DB_POOL_TIMEOUT=30s "
                                        "in database.yaml."
                                    ),
                                    "tags": ["database", "fix", "pool-exhaustion"],
                                },
                            }
                        }
                    ],
                }
            else:
                # Step 4: Model synthesizes final answer to user
                return {
                    "role": "assistant",
                    "content": (
                        "I have inspected the application error logs and diagnosed a "
                        "database connection pool exhaustion. I referenced the local DB "
                        "Pool Runbook and recorded a fix note at the local notes repository."
                    ),
                    "tool_calls": [],
                }

        # 5. Run SovereignAgentLoop
        agent = SovereignAgentLoop(
            search_tool=search_tool,
            file_reader_tool=file_tool,
            note_tool=note_tool,
            command_tool=command_tool,
            chat_executor=simulated_ollama_chat,
        )

        user_prompt = (
            "Inspect the error logs from my local application, find what went wrong, "
            "and make a note about the fix."
        )
        result: AgentRunResult = await agent.run(prompt=user_prompt)

        # 6. Assertions on trace and outcome
        assert result.total_tool_calls == 3
        assert len(result.actions_taken) == 3

        # Sequence must be logical without thrashing
        tool_names = [a.tool_name for a in result.actions_taken]
        assert tool_names == [
            "read_system_file",
            "search_local_knowledge",
            "create_note",
        ]

        # Verify all tool calls succeeded
        assert all(a.success for a in result.actions_taken)

        # Verify note file exists and has frontmatter + fix content
        created_notes = list(notes_dir.glob("*.md"))
        assert len(created_notes) == 1
        note_text = created_notes[0].read_text(encoding="utf-8")

        assert 'title: "Database Connection Pool Fix"' in note_text
        assert "tags: [" in note_text
        assert "Increase DB_POOL_MAX to 50" in note_text

        # Verify final answer text
        assert "database connection pool exhaustion" in result.final_answer.lower()
