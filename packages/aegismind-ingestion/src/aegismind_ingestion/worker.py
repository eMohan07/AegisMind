from __future__ import annotations

import logging
from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort
from aegismind_types import Record
from pydantic import BaseModel, ConfigDict, Field

from aegismind_ingestion.ports import IngestionPipelinePort, IngestionSummary
from aegismind_ingestion.workflow_dbos import DurableWorkflowEngine

logger = logging.getLogger(__name__)


class ScribeSyncReport(BaseModel):
    """Execution summary report from a Scribe sync worker run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    status: str = Field(default="COMPLETED")
    records_synced: int = Field(default=0)
    chunks_indexed: int = Field(default=0)
    tuples_written: int = Field(default=0)
    final_cursor: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class ScribeWorker:
    """Durable sync worker coordinating connectors, cursor state, and ingestion."""

    def __init__(
        self,
        pipeline: IngestionPipelinePort,
        workflow_engine: DurableWorkflowEngine | None = None,
        batch_size: int = 50,
    ) -> None:
        self.pipeline = pipeline
        self.workflow_engine = workflow_engine or DurableWorkflowEngine()
        self.batch_size = batch_size

    async def run_sync(
        self,
        run_id: str,
        connector: ConnectorPort,
        initial_cursor: dict[str, Any] | None = None,
    ) -> ScribeSyncReport:
        """Execute durable connector sync run with cursor management and replayability."""
        logger.info(
            "Starting Scribe sync run '%s' for connector '%s'", run_id, connector.spec().name
        )

        workflow = self.workflow_engine.start_workflow(run_id, initial_cursor)
        current_cursor = dict(workflow.cursor)

        total_records = 0
        total_chunks = 0
        total_tuples = 0
        all_errors: list[str] = []

        batch_number = 1
        current_batch: list[Record] = []

        try:
            # Stream records from connector using current cursor
            async for record in connector.read(state=current_cursor):
                current_batch.append(record)
                total_records += 1

                # Update cursor state candidate from record updated_at or external_id
                current_cursor["last_record_id"] = record.id
                current_cursor["last_updated_at"] = record.updated_at.isoformat()

                if len(current_batch) >= self.batch_size:
                    summary: IngestionSummary = await self.workflow_engine.execute_step(
                        run_id,
                        f"ingest_batch_{batch_number}",
                        self.pipeline.ingest_records,
                        current_batch,
                    )
                    total_chunks += summary.chunks_indexed
                    total_tuples += summary.tuples_written
                    all_errors.extend(summary.errors)

                    # Checkpoint cursor state
                    self.workflow_engine.checkpoint_cursor(run_id, current_cursor)
                    current_batch.clear()
                    batch_number += 1

            # Ingest final batch if remaining
            if current_batch:
                final_summary: IngestionSummary = await self.workflow_engine.execute_step(
                    run_id,
                    f"ingest_batch_{batch_number}",
                    self.pipeline.ingest_records,
                    current_batch,
                )
                total_chunks += final_summary.chunks_indexed
                total_tuples += final_summary.tuples_written
                all_errors.extend(final_summary.errors)
                self.workflow_engine.checkpoint_cursor(run_id, current_cursor)
                current_batch.clear()

            self.workflow_engine.complete_workflow(run_id)

            return ScribeSyncReport(
                run_id=run_id,
                status="COMPLETED",
                records_synced=total_records,
                chunks_indexed=total_chunks,
                tuples_written=total_tuples,
                final_cursor=current_cursor,
                errors=all_errors,
            )
        except Exception as exc:
            logger.error("Scribe sync run '%s' failed: %s", run_id, exc)
            return ScribeSyncReport(
                run_id=run_id,
                status="FAILED",
                records_synced=total_records,
                chunks_indexed=total_chunks,
                tuples_written=total_tuples,
                final_cursor=current_cursor,
                errors=[*all_errors, str(exc)],
            )


async def run_worker_daemon() -> None:
    """Run persistent ingestion worker listening for scheduled sync tasks."""
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("AegisMind Scribe worker daemon initialized and listening for sync tasks.")
    stop_event = asyncio.Event()
    await stop_event.wait()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_worker_daemon())
