from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HybridWeights(BaseModel):
    """Scoring weights for the hybrid retrieval formula."""

    model_config = ConfigDict(frozen=True)

    relevance: float = Field(
        default=0.55, ge=0.0, le=1.0,
        description="Weight for RRF relevance (FTS5 + cosine fused)",
    )
    importance: float = Field(
        default=0.25, ge=0.0, le=1.0,
        description="Weight for memory.importance field",
    )
    recency: float = Field(
        default=0.20, ge=0.0, le=1.0,
        description="Weight for recency decay term",
    )
    pin_boost: float = Field(
        default=0.05, ge=0.0, le=1.0,
        description="Additive bonus applied to pinned memories",
    )


class MemorySettings(BaseModel):
    """Central configuration object for the memory subsystem."""

    model_config = ConfigDict(frozen=True)

    weights: HybridWeights = Field(default_factory=HybridWeights)

    # Recency: half-life in days for exponential decay
    recency_half_life_days: float = Field(default=30.0, gt=0.0)

    # Deduplication: cosine threshold above which a candidate updates existing memory
    dedup_similarity_threshold: float = Field(default=0.90, ge=0.0, le=1.0)

    # Contradiction: cosine threshold for selecting candidates to test
    contradiction_similarity_threshold: float = Field(default=0.75, ge=0.0, le=1.0)

    # Reciprocal Rank Fusion constant
    rrf_k: int = Field(default=60, ge=1)

    # Maximum memories injected into chat context per request
    top_k: int = Field(default=5, ge=1, le=50)

    # Approximate token budget for injected context
    token_budget: int = Field(default=500, ge=100)

    # Rough characters-per-token ratio (used for budget trimming)
    chars_per_token: float = Field(default=4.0, gt=0.0)

    # Hard-purge forgotten memories after this many days
    purge_after_days: int = Field(default=30, ge=1)

    # Auto-extraction: trigger after thread has been idle this many seconds
    extraction_idle_seconds: float = Field(default=300.0, gt=0.0)

    # Maximum candidate memories extracted per thread per run
    max_extraction_candidates: int = Field(default=10, ge=1, le=50)

    # Consolidation: archive memories whose importance falls below this after 60 idle days
    archive_importance_threshold: float = Field(default=0.15, ge=0.0, le=1.0)


# Module-level default instance
DEFAULT_SETTINGS: MemorySettings = MemorySettings()
