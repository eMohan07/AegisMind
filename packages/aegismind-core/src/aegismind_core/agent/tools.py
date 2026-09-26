from __future__ import annotations

import asyncio
import logging
import re
import shlex
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aegismind_retrieval.ports import EmbedderPort, VectorStorePort

from aegismind_core.agent.ports import (
    LocalKnowledgeSearchPort,
    NoteCreatorPort,
    SandboxedCommandRunnerPort,
    SystemFileReaderPort,
)

logger = logging.getLogger(__name__)

FORBIDDEN_SHELL_METACHARACTERS = [";", "|", "&", "`", "$(", "${", ">", "<", "\n", "\r"]

ALLOWED_COMMAND_PREFIXES: list[list[str]] = [
    ["git", "status"],
    ["git", "log"],
    ["docker", "ps"],
    ["docker", "logs"],
    ["tail"],
    ["Get-Content"],
    ["powershell", "Get-Content"],
    ["powershell.exe", "Get-Content"],
]


class LocalKnowledgeSearchAdapter(LocalKnowledgeSearchPort):
    """Adapter for searching the local vector index."""

    def __init__(
        self,
        vector_store: VectorStorePort,
        embedder: EmbedderPort,
    ) -> None:
        self.vector_store = vector_store
        self.embedder = embedder

    async def search(self, query: str, top_k: int = 5) -> str:
        clean_q = query.strip()
        if not clean_q:
            return "No search query provided."
        try:
            emb = await self.embedder.embed_query(clean_q)
            results = await self.vector_store.query_dense(emb, top_k=top_k)
            if not results:
                return f"No matching local knowledge chunks found for query: '{clean_q}'"

            lines = [f"Found {len(results)} relevant local chunks:"]
            for idx, sc in enumerate(results, start=1):
                chunk = sc.chunk
                title = chunk.metadata.get("title") or chunk.document_id
                path = chunk.metadata.get("path") or chunk.metadata.get("uri") or "unknown"
                lines.append(f"{idx}. [{title}] (Score: {sc.score:.2f}, Source: {path})")
                lines.append(f"   {chunk.content.strip()}")
            return "\n".join(lines)
        except Exception as exc:
            logger.error("Local knowledge search failed: %s", exc)
            return f"Search error: {exc}"


class SystemFileReaderAdapter(SystemFileReaderPort):
    """Adapter for reading system files strictly within allowlisted directory roots."""

    def __init__(self, allowed_roots: Sequence[str | Path]) -> None:
        self.allowed_roots = [Path(r).resolve() for r in allowed_roots]

    async def read_file(self, path: str) -> str:
        clean_path = path.strip().strip("'\"")
        # 1. Reject any path containing '..' after normalization
        if ".." in clean_path.replace("\\", "/").split("/"):
            return f"ACCESS_DENIED: Path traversal ('..') is strictly rejected: {clean_path}"

        try:
            target = Path(clean_path).resolve()  # noqa: ASYNC240
        except Exception as exc:
            return f"INVALID_PATH: Could not resolve path '{clean_path}': {exc}"

        # 2. Check if target is inside at least one allowlisted root
        is_allowed = any(target == root or root in target.parents for root in self.allowed_roots)
        if not is_allowed:
            allowed_dirs_str = ", ".join(str(r) for r in self.allowed_roots)
            return (
                f"ACCESS_DENIED: Path '{target}' is outside allowlisted roots: [{allowed_dirs_str}]"
            )

        if not target.exists():
            return f"FILE_NOT_FOUND: File '{target}' does not exist."

        if target.is_dir():
            return f"IS_DIRECTORY: Path '{target}' is a directory, not a readable file."

        try:
            stat = target.stat()
            # Cap reading at 500 KB to avoid memory exhaustion
            if stat.st_size > 512 * 1024:
                with target.open("r", encoding="utf-8", errors="replace") as f:
                    content = f.read(512 * 1024)
                return f"{content}\n\n[WARNING: File truncated at 512 KB]"

            return target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Failed reading file %s: %s", target, exc)
            return f"READ_ERROR: Could not read file '{target}': {exc}"


class NoteCreatorAdapter(NoteCreatorPort):
    """Adapter for writing structured markdown notes with YAML frontmatter."""

    def __init__(self, notes_dir: str | Path = "./storage/notes") -> None:
        self.notes_dir = Path(notes_dir).resolve()
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    async def create_note(
        self,
        title: str,
        content: str,
        tags: list[str],
        source_query: str | None = None,
    ) -> str:
        clean_title = title.strip() or "Untitled Note"
        created_at_dt = datetime.now(UTC)
        time_slug = created_at_dt.strftime("%Y%m%d_%H%M%S")
        title_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", clean_title.lower()).strip("-")[:40]
        filename = f"{time_slug}_{title_slug}.md" if title_slug else f"{time_slug}_note.md"
        note_path = self.notes_dir / filename

        escaped_tags = [t.strip().replace('"', "") for t in tags if t.strip()]
        tags_yaml = ", ".join(f'"{t}"' for t in escaped_tags)

        frontmatter = (
            f"---\n"
            f'title: "{clean_title.replace('"', '\\"')}"\n'
            f"tags: [{tags_yaml}]\n"
            f'created_at: "{created_at_dt.isoformat()}"\n'
            f'source_query: "{(source_query or "").replace('"', '\\"')}"\n'
            f"---\n\n"
        )

        full_content = frontmatter + content.strip() + "\n"

        try:
            note_path.write_text(full_content, encoding="utf-8")
            logger.info("Created local note at %s", note_path)
            return (
                f"NOTE_CREATED: Successfully saved note '{clean_title}' to {note_path.as_posix()}"
            )
        except Exception as exc:
            logger.error("Failed creating note at %s: %s", note_path, exc)
            return f"NOTE_CREATION_FAILED: {exc}"


class SandboxedCommandRunnerAdapter(SandboxedCommandRunnerPort):
    """Adapter for running allowlisted diagnostic commands in a strict sandbox."""

    def __init__(
        self,
        audit_recorder: Callable[..., Any] | None = None,
        working_dir: str | Path | None = None,
        timeout_seconds: float = 10.0,
        output_limit_bytes: int = 100 * 1024,
    ) -> None:
        self.audit_recorder = audit_recorder
        self.working_dir = Path(working_dir).resolve() if working_dir else Path.cwd()
        self.timeout_seconds = timeout_seconds
        self.output_limit_bytes = output_limit_bytes

    def _is_command_allowlisted(self, argv: list[str]) -> bool:
        if not argv:
            return False
        clean_argv = [a.lower().strip() for a in argv]

        for prefix in ALLOWED_COMMAND_PREFIXES:
            prefix_lower = [p.lower().strip() for p in prefix]
            if (
                len(clean_argv) >= len(prefix_lower)
                and clean_argv[: len(prefix_lower)] == prefix_lower
            ):
                return True
        return False

    async def run_command(self, cmd: str) -> str:
        clean_cmd = cmd.strip()

        # 1. Shell metacharacter check (Rejection before execution)
        for char in FORBIDDEN_SHELL_METACHARACTERS:
            if char in clean_cmd:
                err_msg = (
                    f"COMMAND_REJECTED: Command contains forbidden shell metacharacter '{char}'. "
                    "Only raw diagnostic argument execution is permitted."
                )
                if self.audit_recorder:
                    self.audit_recorder(
                        event_type="agent_tool",
                        principal_id="local_agent",
                        action="run_local_command_rejected",
                        metadata={"command": clean_cmd, "reason": "forbidden_metacharacter"},
                    )
                return err_msg

        # 2. Parse into argv without invoking a shell
        try:
            argv = shlex.split(clean_cmd, posix=(sys.platform != "win32"))
        except Exception as exc:
            return f"COMMAND_PARSE_ERROR: Could not parse command arguments: {exc}"

        # 3. Allowlist validation
        if not self._is_command_allowlisted(argv):
            err_msg = (
                f"COMMAND_REJECTED: Command '{clean_cmd}' is not in the diagnostic allowlist. "
                "Permitted commands: git status, git log, docker ps, docker logs, tail, "
                "Get-Content."
            )
            if self.audit_recorder:
                self.audit_recorder(
                    event_type="agent_tool",
                    principal_id="local_agent",
                    action="run_local_command_rejected",
                    metadata={"command": clean_cmd, "reason": "not_allowlisted"},
                )
            return err_msg

        # 4. Execute directly as subprocess without shell=True
        start_time = datetime.now(UTC)
        exit_code = -1
        output = ""

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout_seconds
                )
                exit_code = proc.returncode if proc.returncode is not None else 0
                out_str = stdout_data.decode("utf-8", errors="replace")
                err_str = stderr_data.decode("utf-8", errors="replace")
                combined = out_str + (f"\nSTDERR:\n{err_str}" if err_str else "")

                if len(combined.encode("utf-8")) > self.output_limit_bytes:
                    combined = combined[: self.output_limit_bytes] + "\n[OUTPUT TRUNCATED]"
                output = combined.strip() or "[Command executed with empty output]"
            except TimeoutError:
                proc.kill()
                exit_code = -9
                output = f"COMMAND_TIMEOUT: Execution exceeded {self.timeout_seconds}s timeout."
        except Exception as exc:
            logger.warning("Subprocess execution failed: %s", exc)
            output = f"COMMAND_EXECUTION_ERROR: {exc}"

        # 5. Audit ledger logging
        if self.audit_recorder:
            self.audit_recorder(
                event_type="agent_tool",
                principal_id="local_agent",
                action="run_local_command",
                metadata={
                    "command": clean_cmd,
                    "argv": argv,
                    "working_directory": str(self.working_dir),
                    "exit_code": exit_code,
                    "timestamp": start_time.isoformat(),
                    "output_excerpt": output[:200],
                },
            )

        return output
