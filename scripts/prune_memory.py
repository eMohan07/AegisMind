from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from aegismind_core.memory.models import MemoryFilter, MemoryStatus
from aegismind_core.memory.sqlite_store import SQLiteMemoryStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("prune_memory")


async def prune_memories(
    db_path: str,
    namespace: str | None = None,
    status_target: str | None = None,
    purge_forgotten: bool = False,
    dry_run: bool = False,
) -> int:
    """Scan and prune memories based on provided criteria."""
    path = Path(db_path)
    if not path.exists():
        logger.error("Database not found at %s", db_path)
        return 1

    store = SQLiteMemoryStore(db_path=str(path))
    logger.info("Connected to long-term memory store at %s", db_path)

    # 1. Direct purge of forgotten tombstones if requested
    if purge_forgotten:
        if dry_run:
            logger.info("[Dry Run] Would invoke store.purge_forgotten()")
        else:
            purged = await store.purge_forgotten()
            logger.info("Purged %d forgotten memory tombstones past retention period", purged)

    # 2. Filter-based scanning and pruning
    statuses: list[MemoryStatus] | None = None
    if status_target:
        try:
            statuses = [MemoryStatus(status_target.lower())]
        except ValueError:
            logger.error("Invalid status target: '%s'", status_target)
            return 1

    filters = MemoryFilter(
        namespace=namespace,
        statuses=statuses,
        limit=500,
    )

    records = await store.list(filters)
    logger.info("Found %d records matching filter criteria", len(records))

    if not records:
        logger.info("Nothing to prune.")
        return 0

    action_count = 0
    for record in records:
        if dry_run:
            logger.info(
                "[Dry Run] Candidate ID: %s | Status: %s | Type: %s | Content: %s...",
                record.id,
                record.status,
                record.type,
                record.content[:60],
            )
        else:
            if record.status in (MemoryStatus.REJECTED, MemoryStatus.FORGOTTEN):
                logger.info("Removing %s memory record %s", record.status, record.id)
                conn = store._conn()
                conn.execute("DELETE FROM memories WHERE id = ?", (record.id,))
                conn.commit()
                action_count += 1

    if dry_run:
        logger.info("[Dry Run] Completed scan of %d memories. No changes made.", len(records))
    else:
        logger.info("Successfully pruned %d memories.", action_count)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AegisMind Long-Term Memory Pruning Tool",
    )
    parser.add_argument(
        "--db-path",
        default="./storage/memory/ltm.db",
        help="Path to SQLite memory database (default: ./storage/memory/ltm.db)",
    )
    parser.add_argument(
        "--namespace",
        default=None,
        help="Target namespace filter (default: None for all namespaces)",
    )
    parser.add_argument(
        "--status",
        choices=["pending", "rejected", "forgotten", "superseded", "active"],
        default=None,
        help="Filter by memory status",
    )
    parser.add_argument(
        "--purge-forgotten",
        action="store_true",
        help="Purge tombstoned forgotten memories older than retention window",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect candidate memories without applying deletions",
    )

    args = parser.parse_args()

    return asyncio.run(
        prune_memories(
            db_path=args.db_path,
            namespace=args.namespace,
            status_target=args.status,
            purge_forgotten=args.purge_forgotten,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
