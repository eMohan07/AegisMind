from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

from aegismind_core.agent.ports import (
    LocalKnowledgeSearchPort,
    NoteCreatorPort,
    SandboxedCommandRunnerPort,
    SystemFileReaderPort,
    ToolActionResult,
)

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
        ollama_url: str | None = None,
        model: str | None = None,
        audit_recorder: Callable[..., Any] | None = None,
        max_tool_calls_per_turn: int = 6,
        chat_executor: Callable[[list[dict[str, Any]], list[dict[str, Any]]], Any] | None = None,
    ) -> None:
        self.search_tool = search_tool
        self.file_reader_tool = file_reader_tool
        self.note_tool = note_tool
        self.command_tool = command_tool
        self.ollama_url = (
            ollama_url or os.environ.get("OLLAMA_URL") or "http://localhost:11434"
        ).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_AGENT_MODEL") or "qwen2.5:7b"
        self.audit_recorder = audit_recorder
        self.max_tool_calls_per_turn = max_tool_calls_per_turn
        self.chat_executor = chat_executor

    async def _execute_tool(self, name: str, args: dict[str, Any], query: str) -> ToolActionResult:
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
            else:
                res_text = f"UNKNOWN_TOOL: Tool '{name}' is not recognized."
                success = False
        except Exception as exc:
            logger.error("Error executing tool %s: %s", name, exc)
            res_text = f"TOOL_EXECUTION_ERROR: {exc}"
            success = False

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
                },
            )

        return action_result

    async def _call_model(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Call Ollama /api/chat with tools payload or use custom chat_executor."""
        if self.chat_executor is not None:
            res = self.chat_executor(messages, tools)
            if hasattr(res, "__await__"):
                return await res  # type: ignore[no-any-return]
            return res  # type: ignore[no-any-return]

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
            "read_system_file, create_note, and run_local_command.\n"
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

            # If no tool calls were requested, model has returned its final synthesized answer
            if not tool_calls:
                final_content = assistant_msg.get("content", "").strip()
                duration = (datetime.now(UTC) - start_ts).total_seconds() * 1000.0
                return AgentRunResult(
                    final_answer=final_content,
                    actions_taken=actions_taken,
                    total_tool_calls=total_calls,
                    duration_ms=round(duration, 2),
                )

            # Process tool calls
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

                action_result = await self._execute_tool(tool_name, args, query=prompt)
                actions_taken.append(action_result)
                total_calls += 1

                # Feed tool result back into conversation history
                messages.append(
                    {
                        "role": "tool",
                        "content": action_result.result,
                        "name": tool_name,
                    }
                )

        # Reached tool limit without final answer: ask for final synthesis
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
