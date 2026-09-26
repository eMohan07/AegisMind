from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ToolActionResult(BaseModel):
    """Structured record of an action taken by a local sovereign agent tool."""

    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(..., description="Name of the invoked tool")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments passed to tool")
    result: str = Field(..., description="Execution outcome or text summary returned to model")
    success: bool = Field(default=True, description="Whether tool execution succeeded")
    timestamp: str = Field(..., description="ISO 8601 timestamp of execution")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Optional diagnostic details"
    )


@runtime_checkable
class LocalKnowledgeSearchPort(Protocol):
    """Port for querying the local sovereign vector index."""

    async def search(self, query: str, top_k: int = 5) -> str:
        """Query local vector index and return formatted chunks with paths and scores."""
        ...


@runtime_checkable
class SystemFileReaderPort(Protocol):
    """Port for reading local system files with directory allowlist validation."""

    async def read_file(self, path: str) -> str:
        """Read file contents safely, rejecting paths outside allowlisted root directories."""
        ...


@runtime_checkable
class NoteCreatorPort(Protocol):
    """Port for persisting structured markdown notes with YAML frontmatter."""

    async def create_note(
        self,
        title: str,
        content: str,
        tags: list[str],
        source_query: str | None = None,
    ) -> str:
        """Write note to disk and return confirmation with file path."""
        ...


@runtime_checkable
class SandboxedCommandRunnerPort(Protocol):
    """Port for running allowlisted diagnostic commands without shell invocation."""

    async def run_command(self, cmd: str) -> str:
        """Execute sandboxed command against strict allowlist, recording audit trail."""
        ...
