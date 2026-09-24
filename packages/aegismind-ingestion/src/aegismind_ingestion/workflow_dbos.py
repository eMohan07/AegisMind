from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class WorkflowStepRecord(BaseModel):
    """Execution audit trail for a durable workflow step."""

    model_config = ConfigDict(frozen=True)

    step_name: str
    status: str = Field(default="COMPLETED")
    output: Any = Field(default=None)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkflowState(BaseModel):
    """Durable state container for a workflow instance."""

    run_id: str
    status: str = Field(default="RUNNING")
    steps: dict[str, WorkflowStepRecord] = Field(default_factory=dict)
    cursor: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    error: str | None = None


class DurableWorkflowEngine:
    """Lightweight durable execution engine providing step checkpointing and replayability."""

    def __init__(self) -> None:
        self._runs: dict[str, WorkflowState] = {}

    def start_workflow(
        self, run_id: str, initial_cursor: dict[str, Any] | None = None
    ) -> WorkflowState:
        """Initialize or retrieve a durable workflow state."""
        if run_id in self._runs:
            logger.info("Resuming durable workflow run '%s'", run_id)
            return self._runs[run_id]

        state = WorkflowState(
            run_id=run_id,
            status="RUNNING",
            cursor=initial_cursor or {},
        )
        self._runs[run_id] = state
        logger.info("Initialized durable workflow run '%s'", run_id)
        return state

    async def execute_step[T](
        self,
        run_id: str,
        step_name: str,
        step_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute a durable step with replay protection.

        If the step was already executed in a previous attempt of this workflow run,
        its cached result is returned without re-executing side effects.
        """
        state = self._runs[run_id]

        # Check if step has already been recorded (idempotent replay)
        if step_name in state.steps:
            logger.debug("Replaying cached result for durable step '%s'", step_name)
            return state.steps[step_name].output  # type: ignore[no-any-return]

        try:
            logger.debug("Executing durable step '%s'", step_name)
            import asyncio

            if asyncio.iscoroutinefunction(step_fn):
                result = await step_fn(*args, **kwargs)
            else:
                result = step_fn(*args, **kwargs)

            # Record step checkpoint
            record = WorkflowStepRecord(
                step_name=step_name,
                status="COMPLETED",
                output=result,
            )
            state.steps[step_name] = record
            return result  # type: ignore[no-any-return]
        except Exception as exc:
            state.status = "FAILED"
            state.error = str(exc)
            logger.error("Durable step '%s' failed in run '%s': %s", step_name, run_id, exc)
            raise

    def checkpoint_cursor(self, run_id: str, cursor: dict[str, Any]) -> None:
        """Update and checkpoint cursor state."""
        state = self._runs[run_id]
        state.cursor = dict(cursor)
        logger.debug("Checkpointed cursor state for run '%s'", run_id)

    def complete_workflow(self, run_id: str) -> None:
        """Mark workflow as successfully completed."""
        state = self._runs[run_id]
        state.status = "COMPLETED"
        state.completed_at = datetime.now(UTC)
        logger.info("Completed durable workflow run '%s'", run_id)

    def get_state(self, run_id: str) -> WorkflowState | None:
        """Retrieve state of a workflow run."""
        return self._runs.get(run_id)
