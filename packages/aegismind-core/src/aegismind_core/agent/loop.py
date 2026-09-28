from __future__ import annotations

import json
import logging
import os
import re
import shlex
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

from aegismind_core.agent.activity import LocalToolActivityRecorder
from aegismind_core.agent.ports import (
    LocalKnowledgeSearchPort,
    NoteCreatorPort,
    SandboxedCommandRunnerPort,
    SaveMemoryPort,
    SystemFileReaderPort,
    ToolActionResult,
)
from aegismind_core.agent.tools import IMAGE_EXTENSIONS
from aegismind_core.approvals import Proposal, RiskLevel, evaluate
from aegismind_core.approvals.store import ApprovalStore

logger = logging.getLogger(__name__)

OLLAMA_TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_local_knowledge",
            "description": (
                "Query the local vector index for relevant documentation, code, "
                "or indexed knowledge chunks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string"},
                    "top_k": {
                        "type": "integer",
                        "description": "Maximum candidate chunks to return (default: 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_system_file",
            "description": (
                "Read a local file within allowlisted directories. Validates paths against "
                "an explicit directory allowlist and strictly rejects path traversal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": (
                "Write a structured markdown note with YAML frontmatter (title, tags, created_at) "
                "to the local notes directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the note"},
                    "content": {"type": "string", "description": "Markdown body content"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tags",
                    },
                },
                "required": ["title", "content", "tags"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_local_command",
            "description": (
                "Execute a sandboxed, read-only diagnostic command (git status, git log, "
                "docker ps, docker logs, tail, Get-Content). Shell metacharacters are forbidden."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "Diagnostic command string without shell metacharacters",
                    },
                },
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save a fact to long-term memory with tags. This action requires "
                "user approval before being executed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "The fact to save"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for the fact",
                    },
                },
                "required": ["fact", "tags"],
            },
        },
    },
]


class AgentRunResult(BaseModel):
    """Final outcome of a SovereignAgentLoop execution."""

    model_config = ConfigDict(frozen=True)

    final_answer: str = Field(..., description="Final textual answer synthesized for user")
    actions_taken: list[ToolActionResult] = Field(
        default_factory=list,
        description="Structured chronological list of all tool actions executed",
    )
    total_tool_calls: int = Field(default=0)
    duration_ms: float = Field(default=0.0)


class SovereignAgentLoop:
    """ReAct autonomous tool-calling loop connecting local Ollama to sandboxed system tools."""

    def __init__(
        self,
        search_tool: LocalKnowledgeSearchPort,
        file_reader_tool: SystemFileReaderPort,
        note_tool: NoteCreatorPort,
        command_tool: SandboxedCommandRunnerPort,
        save_memory_tool: SaveMemoryPort | None = None,
        approval_store: ApprovalStore | None = None,
        ollama_url: str | None = None,
        model: str | None = None,
        audit_recorder: Callable[..., Any] | None = None,
        activity_recorder: LocalToolActivityRecorder | None = None,
        max_tool_calls_per_turn: int = 6,
        chat_executor: Callable[[list[dict[str, Any]], list[dict[str, Any]]], Any] | None = None,
    ) -> None:
        self.search_tool = search_tool
        self.file_reader_tool = file_reader_tool
        self.note_tool = note_tool
        self.command_tool = command_tool
        self.save_memory_tool = save_memory_tool
        self.approval_store = approval_store
        self.ollama_url = (
            ollama_url or os.environ.get("OLLAMA_URL") or "http://localhost:11434"
        ).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_AGENT_MODEL") or "qwen2.5:7b"
        self.audit_recorder = audit_recorder
        self.activity_recorder = activity_recorder
        self.max_tool_calls_per_turn = max_tool_calls_per_turn
        self.chat_executor = chat_executor

    def _classify_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """Classify a tool call as 'auto', 'approval', or 'deny'."""
        if self.approval_store is None:
            return "auto"
        return evaluate(tool_name, args)

    async def _execute_tool(self, name: str, args: dict[str, Any], query: str) -> ToolActionResult:
        approval_required = name in ("run_local_command", "create_note")
        active_event = None
        if self.activity_recorder:
            active_event = self.activity_recorder.record_start(
                tool_name=name,
                parameters=args,
                agent_id="local_agent",
                approval_required=approval_required,
            )

        start_time = time.perf_counter()
        timestamp_str = datetime.now(UTC).isoformat()
        res_text = ""
        success = True

        try:
            if name == "search_local_knowledge":
                q = str(args.get("query", ""))
                top_k = int(args.get("top_k", 5))
                res_text = await self.search_tool.search(query=q, top_k=top_k)
            elif name == "read_system_file":
                p = str(args.get("path", ""))
                res_text = await self.file_reader_tool.read_file(path=p)
                if res_text.startswith("ACCESS_DENIED") or res_text.startswith("FILE_NOT_FOUND"):
                    success = False
            elif name == "create_note":
                title = str(args.get("title", "Untitled Note"))
                content = str(args.get("content", ""))
                raw_tags = args.get("tags", [])
                tags = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else ["agent"]
                res_text = await self.note_tool.create_note(
                    title=title,
                    content=content,
                    tags=tags,
                    source_query=query,
                )
            elif name == "run_local_command":
                cmd = str(args.get("cmd", ""))
                res_text = await self.command_tool.run_command(cmd=cmd)
                if res_text.startswith("COMMAND_REJECTED") or res_text.startswith(
                    "COMMAND_PARSE_ERROR"
                ):
                    success = False
            elif name == "save_memory":
                if self.save_memory_tool is not None:
                    fact = str(args.get("fact", ""))
                    raw_tags = args.get("tags", [])
                    tags = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
                    res_text = await self.save_memory_tool.save_memory(fact=fact, tags=tags)
                else:
                    res_text = "SAVE_MEMORY_FAILED: save_memory tool not configured"
                    success = False
            else:
                res_text = f"UNKNOWN_TOOL: Tool '{name}' is not recognized."
                success = False
        except Exception as exc:
            logger.error("Error executing tool %s: %s", name, exc)
            res_text = f"TOOL_EXECUTION_ERROR: {exc}"
            success = False
        finally:
            if self.activity_recorder and active_event:
                self.activity_recorder.record_complete(
                    event_id=active_event.event_id,
                    status="success" if success else "failed",
                    duration_ms=(time.perf_counter() - start_time) * 1000.0,
                    result_summary=res_text[:300],
                    error=res_text if not success else None,
                )

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        action_result = ToolActionResult(
            tool_name=name,
            arguments=args,
            result=res_text,
            success=success,
            timestamp=timestamp_str,
        )

        if self.audit_recorder:
            self.audit_recorder(
                event_type="agent_tool",
                principal_id="local_agent",
                action=f"invoke_{name}",
                metadata={
                    "arguments": args,
                    "success": success,
                    "result_summary": res_text[:200],
                    "duration_ms": round(duration_ms, 2),
                },
            )

        return action_result

    def _create_proposal(
        self, tool_name: str, args: dict[str, Any], risk: str, reasoning: str, preview: str
    ) -> Proposal:
        """Create a Proposal for an approval-required tool."""
        proposal = Proposal(
            tool_name=tool_name,
            args=args,
            risk=RiskLevel(risk),
            reasoning=reasoning,
            preview=preview,
            source_refs=[],
            tainted=False,
            taint_sources=[],
        )
        if self.approval_store is not None:
            self.approval_store.create(proposal)
        logger.info("Created proposal %s for tool %s", proposal.id, tool_name)
        return proposal

    def _build_preview(self, tool_name: str, args: dict[str, Any]) -> str:
        """Build a preview for the proposal."""
        if tool_name == "create_note":
            return json.dumps(args)
        if tool_name == "run_local_command":
            cmd = str(args.get("cmd", ""))
            try:
                argv = shlex.split(cmd.strip(), posix=(sys.platform != "win32"))
                return str(argv)
            except Exception:
                return cmd
        return json.dumps(args)

    @staticmethod
    def _filter_image_content(text: str) -> str:
        """Filter out image-related content from tool results."""
        lines = []
        for line in text.split("\n"):
            if IMAGE_EXTENSIONS and any(ext in line.lower() for ext in IMAGE_EXTENSIONS):
                continue
            lines.append(line)
        return "\n".join(lines) if lines else text

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Remove ANSI escape codes, control characters, and excessive Unicode."""
        text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
        text = text.replace("\ufeff", "")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        return text

    async def _call_model(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Call Ollama /api/chat with tools payload or use custom chat_executor."""
        if self.chat_executor is not None:
            res = self.chat_executor(messages, tools)
            if hasattr(res, "__await__"):
                return cast(dict[str, Any], await res)
            return cast(dict[str, Any], res)

        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self.ollama_url}/api/chat", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return cast(dict[str, Any], data.get("message", {}))
            logger.warning("Ollama /api/chat returned HTTP %d: %s", resp.status_code, resp.text)
            return {"role": "assistant", "content": f"Ollama error (HTTP {resp.status_code})"}

    async def run(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> AgentRunResult:
        """Run the sovereign ReAct agent loop until final completion or tool call limit."""
        start_ts = datetime.now(UTC)
        default_system = (
            "You are AegisMind Local Sovereign Agent. You operate completely offline on the "
            "user's machine. You have direct access to local tools: search_local_knowledge, "
            "read_system_file, create_note, run_local_command, and save_memory.\n"
            "When the user asks you to inspect system files or logs, search local docs, diagnose "
            "issues, or record notes, use the available tools proactively before providing your "
            "final answer."
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_instruction or default_system},
            {"role": "user", "content": prompt},
        ]

        actions_taken: list[ToolActionResult] = []
        total_calls = 0

        while total_calls < self.max_tool_calls_per_turn:
            try:
                assistant_msg = await self._call_model(messages, OLLAMA_TOOLS_SCHEMA)
            except Exception as exc:
                logger.error("Failed communicating with model: %s", exc)
                return AgentRunResult(
                    final_answer=(
                        f"Local model error: could not connect to Ollama at {self.ollama_url}. "
                        "Please verify Ollama is running (`ollama run qwen2.5:7b` or "
                        "`ollama run llama3.2`)."
                    ),
                    actions_taken=actions_taken,
                    total_tool_calls=total_calls,
                )

            tool_calls = assistant_msg.get("tool_calls", [])
            messages.append(assistant_msg)

            if not tool_calls:
                final_content = assistant_msg.get("content", "").strip()
                duration = (datetime.now(UTC) - start_ts).total_seconds() * 1000.0
                return AgentRunResult(
                    final_answer=final_content,
                    actions_taken=actions_taken,
                    total_tool_calls=total_calls,
                    duration_ms=round(duration, 2),
                )

            for tc in tool_calls:
                if total_calls >= self.max_tool_calls_per_turn:
                    logger.warning(
                        "Reached maximum tool call limit (%d)", self.max_tool_calls_per_turn
                    )
                    break

                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                raw_args = fn.get("arguments", {})
                args: dict[str, Any] = (
                    json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                )

                if self.approval_store is None:
                    classification = "auto"
                else:
                    classification = self._classify_tool(tool_name, args)

                if classification == "deny":
                    filtered_result = self._filter_image_content(
                        f"ACTION_BLOCKED: Tool '{tool_name}' is denied by policy."
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "content": filtered_result,
                            "name": tool_name,
                        }
                    )
                    action_result = ToolActionResult(
                        tool_name=tool_name,
                        arguments=args,
                        result=f"ACTION_BLOCKED: Tool '{tool_name}' is denied by policy.",
                        success=False,
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                    actions_taken.append(action_result)
                    total_calls += 1
                    continue

                if classification == "approval":
                    preview = self._build_preview(tool_name, args)
                    reasoning = f"Agent wants to execute {tool_name}"
                    risk_str = "medium"
                    if tool_name == "save_memory":
                        risk_str = "low"
                    elif tool_name == "create_note":
                        risk_str = "low"
                    elif tool_name == "run_local_command":
                        risk_str = "medium"
                    proposal = self._create_proposal(
                        tool_name=tool_name,
                        args=args,
                        risk=risk_str,
                        reasoning=reasoning,
                        preview=preview,
                    )
                    filtered_result = self._filter_image_content(
                        f"Queued for user approval, do not retry (proposal_id: {proposal.id})"
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "content": filtered_result,
                            "name": tool_name,
                        }
                    )
                    action_result = ToolActionResult(
                        tool_name=tool_name,
                        arguments=args,
                        result=(
                            f"Queued for user approval, do not retry "
                            f"(proposal_id: {proposal.id})"
                        ),
                        success=False,
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                    actions_taken.append(action_result)
                    total_calls += 1
                    continue

                action_result = await self._execute_tool(tool_name, args, query=prompt)
                actions_taken.append(action_result)
                total_calls += 1

                filtered_result = self._filter_image_content(action_result.result)
                messages.append(
                    {
                        "role": "tool",
                        "content": filtered_result,
                        "name": tool_name,
                    }
                )

        messages.append(
            {
                "role": "user",
                "content": (
                    "You have reached the tool execution limit. Please synthesize your final "
                    "diagnosis and response based on the observations collected above."
                ),
            }
        )
        try:
            final_msg = await self._call_model(messages, [])
            final_text = final_msg.get("content", "").strip()
            final_text = self._sanitize_text(final_text)
        except Exception:
            final_text = (
                f"Agent executed {total_calls} actions. Summary of findings:\n"
                + "\n".join(f"- [{a.tool_name}]: {a.result[:100]}" for a in actions_taken)
            )

        duration = (datetime.now(UTC) - start_ts).total_seconds() * 1000.0
        return AgentRunResult(
            final_answer=final_text,
            actions_taken=actions_taken,
            total_tool_calls=total_calls,
            duration_ms=round(duration, 2),
        )
