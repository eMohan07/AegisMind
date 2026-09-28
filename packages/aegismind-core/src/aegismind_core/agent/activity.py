from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

ToolActivityCategory = Literal["filesystem", "knowledge", "sandbox", "notes", "system"]
ToolActivityStatus = Literal["running", "success", "failed"]

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|secret|token|api[_-]?key|auth|credential|cert|private|bearer)",
    re.IGNORECASE,
)

SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9_\-]{16,})"),
    re.compile(r"(ghp_[A-Za-z0-9]{20,})"),
    re.compile(r"(gho_[A-Za-z0-9]{20,})"),
    re.compile(r"(github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"(xox[baprs]-[0-9a-zA-Z]{10,})"),
    re.compile(r"(AKIA[0-9A-Z]{16})"),
    re.compile(r"(--password[=\s]+)\S+", re.IGNORECASE),
    re.compile(r"(-p[=\s]+)\S+", re.IGNORECASE),
    re.compile(r"(PGPASSWORD[=\s]+)\S+", re.IGNORECASE),
]


def infer_tool_category(tool_name: str) -> ToolActivityCategory:
    """Infer category from the tool name according to sovereign domain."""
    name = tool_name.lower().strip()
    if any(k in name for k in ("search", "knowledge", "retriev", "index", "vector")):
        return "knowledge"
    if any(k in name for k in ("file", "read", "directory", "path", "folder", "cat")):
        return "filesystem"
    if any(k in name for k in ("command", "sandbox", "exec", "process", "shell", "run")):
        return "sandbox"
    if any(k in name for k in ("note", "vault", "memo", "study")):
        return "notes"
    return "system"


def sanitize_value(val: Any, key_name: str = "") -> Any:
    """Sanitize individual value, redacting secrets and truncating large payloads."""
    if key_name and SENSITIVE_KEY_PATTERN.search(key_name):
        return "[REDACTED]"

    if isinstance(val, str):
        sanitized = val
        for pat in SENSITIVE_VALUE_PATTERNS:
            sanitized = pat.sub("[REDACTED]", sanitized)
        # Cap large file contents or blobs to prevent leak and log bloat
        if len(sanitized) > 350:
            return sanitized[:300] + " ... [TRUNCATED]"
        return sanitized
    elif isinstance(val, dict):
        return {str(k): sanitize_value(v, str(k)) for k, v in val.items()}
    elif isinstance(val, (list, tuple)):
        return [sanitize_value(v, key_name) for v in val]
    return val


def sanitize_parameters(params: dict[str, Any]) -> dict[str, Any]:
    """Sanitize all input parameters before audit recording."""
    return {str(k): sanitize_value(v, str(k)) for k, v in params.items()}


class ToolActivityEvent(BaseModel):
    """Immutable audit event representing a single local agent tool execution."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    tool_name: str = Field(..., description="Name of the invoked local tool")
    category: ToolActivityCategory = Field(
        ..., description="Tool category (filesystem, knowledge, sandbox, notes, system)"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Sanitized invocation parameters"
    )
    status: ToolActivityStatus = Field(
        default="running", description="Execution status (running, success, failed)"
    )
    duration_ms: float = Field(default=0.0, description="Execution duration in milliseconds")
    agent_id: str = Field(default="local_agent", description="Agent identifier")
    source: str = Field(default="local", description="Execution source boundary")
    approval_required: bool = Field(
        default=False, description="Whether human approval was required"
    )
    error: str | None = Field(default=None, description="Error message when tool failed")
    result_summary: str | None = Field(
        default=None, description="Sanitized result summary or excerpt"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary audit metadata")


class LocalToolActivityRecorder:
    """Centralized, offline, persistent recorder and real-time SSE broadcaster for tool activity."""

    def __init__(
        self,
        storage_path: str | Path = "./storage/activity/tool_events.json",
        max_events: int = 500,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.max_events = max_events
        self._events: list[ToolActivityEvent] = []
        self._active_events: dict[str, float] = {}
        self._subscribers: set[asyncio.Queue[ToolActivityEvent]] = set()
        self._load()

    def _load(self) -> None:
        """Load historical activity from local storage on startup."""
        if not self.storage_path.exists():
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            return

        try:
            raw = self.storage_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                self._events = [ToolActivityEvent.model_validate(item) for item in data][
                    -self.max_events :
                ]
            elif isinstance(data, dict) and "events" in data:
                self._events = [ToolActivityEvent.model_validate(item) for item in data["events"]][
                    -self.max_events :
                ]
            logger.info(
                "Loaded %d local tool activity events from %s",
                len(self._events),
                self.storage_path,
            )
        except Exception as exc:
            logger.warning("Failed to load local tool activity from %s: %s", self.storage_path, exc)
            self._events = []

        self.mark_running_as_interrupted()

    def mark_running_as_interrupted(self) -> int:
        """Mark any leftover 'running' events as 'failed' with 'interrupted' message."""
        count = 0
        for event in self._events:
            if event.status == "running":
                self._events.remove(event)
                interrupted = event.model_copy(
                    update={
                        "status": "failed",
                        "error": "interrupted",
                        "result_summary": "interrupted",
                    }
                )
                self._events.append(interrupted)
                count += 1
        if count > 0:
            self._persist()
        return count

    def _persist(self) -> None:
        """Flush events to local JSON storage."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            dumped = [e.model_dump() for e in self._events]
            self.storage_path.write_text(json.dumps(dumped, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to persist local tool activity: %s", exc)

    def _broadcast(self, event: ToolActivityEvent) -> None:
        """Broadcast event to all connected SSE clients."""
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except Exception as exc:
                logger.debug("Failed delivering event to queue subscriber: %s", exc)

    def subscribe(self) -> asyncio.Queue[ToolActivityEvent]:
        """Subscribe to real-time tool events via an async queue."""
        queue: asyncio.Queue[ToolActivityEvent] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[ToolActivityEvent]) -> None:
        """Unsubscribe queue from broadcaster."""
        self._subscribers.discard(queue)

    def record_start(
        self,
        tool_name: str,
        parameters: dict[str, Any] | None = None,
        agent_id: str = "local_agent",
        approval_required: bool = False,
        category: ToolActivityCategory | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolActivityEvent:
        """Record the start of a tool invocation in 'running' status."""
        event_id = str(uuid.uuid4())
        cat = category or infer_tool_category(tool_name)
        sanitized_params = sanitize_parameters(parameters or {})

        event = ToolActivityEvent(
            event_id=event_id,
            timestamp=datetime.now(UTC).isoformat(),
            tool_name=tool_name,
            category=cat,
            parameters=sanitized_params,
            status="running",
            duration_ms=0.0,
            agent_id=agent_id,
            source="local",
            approval_required=approval_required,
            metadata=metadata or {},
        )

        self._active_events[event_id] = time.perf_counter()
        self._events.append(event)
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events :]

        self._persist()
        self._broadcast(event)
        return event

    def record_complete(
        self,
        event_id: str,
        status: Literal["success", "failed"] = "success",
        duration_ms: float | None = None,
        result_summary: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolActivityEvent | None:
        """Record completion of a running tool event with final status, duration, and output."""
        if duration_ms is None and event_id in self._active_events:
            duration_ms = (time.perf_counter() - self._active_events.pop(event_id)) * 1000.0
        elif event_id in self._active_events:
            self._active_events.pop(event_id)

        duration = round(duration_ms if duration_ms is not None else 0.0, 2)

        target_event: ToolActivityEvent | None = None
        for i, ev in enumerate(self._events):
            if ev.event_id == event_id:
                sanitized_summary = sanitize_value(result_summary) if result_summary else None
                sanitized_error = sanitize_value(error) if error else None
                updated_meta = {**ev.metadata, **(metadata or {})}
                target_event = ev.model_copy(
                    update={
                        "status": status,
                        "duration_ms": duration,
                        "result_summary": sanitized_summary,
                        "error": sanitized_error,
                        "metadata": updated_meta,
                    }
                )
                self._events[i] = target_event
                break

        if target_event:
            self._persist()
            self._broadcast(target_event)

        return target_event

    def record_event(
        self,
        tool_name: str,
        parameters: dict[str, Any] | None = None,
        status: ToolActivityStatus = "success",
        duration_ms: float = 0.0,
        agent_id: str = "local_agent",
        approval_required: bool = False,
        category: ToolActivityCategory | None = None,
        error: str | None = None,
        result_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolActivityEvent:
        """Record an atomic tool event directly (for rejected or single-shot tool executions)."""
        event_id = str(uuid.uuid4())
        cat = category or infer_tool_category(tool_name)
        sanitized_params = sanitize_parameters(parameters or {})
        sanitized_summary = sanitize_value(result_summary) if result_summary else None
        sanitized_error = sanitize_value(error) if error else None

        event = ToolActivityEvent(
            event_id=event_id,
            timestamp=datetime.now(UTC).isoformat(),
            tool_name=tool_name,
            category=cat,
            parameters=sanitized_params,
            status=status,
            duration_ms=round(duration_ms, 2),
            agent_id=agent_id,
            source="local",
            approval_required=approval_required,
            error=sanitized_error,
            result_summary=sanitized_summary,
            metadata=metadata or {},
        )

        self._events.append(event)
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events :]

        self._persist()
        self._broadcast(event)
        return event

    def get_events(
        self,
        category: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ToolActivityEvent]:
        """Return events in reverse chronological order with category and status filters."""
        filtered = self._events
        if category and category.lower() != "all":
            filtered = [e for e in filtered if e.category.lower() == category.lower()]
        if status and status.lower() != "all":
            filtered = [e for e in filtered if e.status.lower() == status.lower()]
        return list(reversed(filtered))[:limit]

    def clear(self) -> None:
        """Clear all stored activity events."""
        self._events = []
        self._active_events.clear()
        self._persist()
