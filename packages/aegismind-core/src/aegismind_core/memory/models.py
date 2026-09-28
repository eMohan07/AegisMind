from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryType(StrEnum):
    """Cognitive type of a stored memory."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"


class MemoryStatus(StrEnum):
    """Lifecycle state of a memory record."""

    PENDING = "pending"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    FORGOTTEN = "forgotten"


class MemorySensitivity(StrEnum):
    """Sensitivity classification for access control hints."""

    NORMAL = "normal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


class Namespace(BaseModel):
    """Logical grouping for memories (e.g. 'global', 'main_chat', 'dataset')."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Unique namespace name")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class MemoryRecord(BaseModel):
    """A single typed, versioned, scored memory entry."""

    model_config = ConfigDict(frozen=False)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    namespace: str = Field(default="global")
    type: MemoryType = Field(default=MemoryType.SEMANTIC)
    content: str = Field(..., description="One atomic fact or memory")
    entities_json: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    status: MemoryStatus = Field(default=MemoryStatus.PENDING)
    pinned: bool = Field(default=False)
    sensitivity: MemorySensitivity = Field(default=MemorySensitivity.NORMAL)
    source_thread_id: str | None = Field(default=None)
    source_message_ids_json: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_accessed_at: str | None = Field(default=None)
    access_count: int = Field(default=0, ge=0)
    valid_from: str | None = Field(default=None)
    valid_to: str | None = Field(default=None)
    superseded_by: str | None = Field(default=None)
    content_hash: str = Field(default="", description="SHA-256 of normalised content")

    @property
    def entities(self) -> list[str]:
        return self.entities_json

    @entities.setter
    def entities(self, val: list[str]) -> None:
        self.entities_json = val


class MemoryEvent(BaseModel):
    """One entry in the append-only, SHA-256 hash-chained audit trail."""

    model_config = ConfigDict(frozen=True)

    seq: int = Field(..., description="Monotonically increasing sequence number")
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    event: str = Field(
        ...,
        description=(
            "Event type: created | updated | approved | rejected | forgotten | "
            "purged | superseded | touched | exported | imported | backup | restore"
        ),
    )
    memory_id: str | None = Field(default=None)
    actor: str = Field(default="system")
    payload: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = Field(default="0" * 64)
    hash: str = Field(default="")


class ScoredMemory(BaseModel):
    """A MemoryRecord paired with its composite retrieval score."""

    model_config = ConfigDict(frozen=True)

    memory: MemoryRecord
    score: float = Field(..., description="Final composite score")
    fts_rank: int = Field(default=0, description="FTS5 rank (lower = better)")
    vector_score: float = Field(default=0.0)
    rrf_score: float = Field(default=0.0)


class MemoryFilter(BaseModel):
    """Criteria for listing or paginating memories."""

    model_config = ConfigDict(frozen=True)

    namespace: str | None = None
    types: list[MemoryType] | None = None
    statuses: list[MemoryStatus] | None = None
    pinned: bool | None = None
    sensitivity: list[MemorySensitivity] | None = None
    text: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    source_thread_id: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
