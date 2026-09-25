from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from aegismind_ingestion.ports import DLQItem, DLQPort

logger = logging.getLogger(__name__)


class MemoryDLQAdapter(DLQPort):
    """In-memory Dead-Letter Queue adapter for local development and test automation."""

    def __init__(self) -> None:
        self._items: dict[str, DLQItem] = {}

    async def enqueue(
        self,
        connector_id: str,
        resource_id: str,
        error_message: str,
        payload: dict[str, Any] | None = None,
    ) -> DLQItem:
        item = DLQItem(
            connector_id=connector_id,
            resource_id=resource_id,
            error_message=error_message,
            payload=payload or {},
        )
        self._items[item.id] = item
        logger.warning(
            "DLQ: Enqueued failed item %s from connector %s (resource=%s): %s",
            item.id,
            connector_id,
            resource_id,
            error_message,
        )
        return item

    async def list_items(
        self,
        connector_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[DLQItem]:
        filtered = list(self._items.values())
        if connector_id:
            filtered = [it for it in filtered if it.connector_id == connector_id]
        if status:
            filtered = [it for it in filtered if it.status == status]
        filtered.sort(key=lambda it: it.last_failed_at, reverse=True)
        return filtered[:limit]

    async def get_item(self, item_id: str) -> DLQItem | None:
        return self._items.get(item_id)

    async def update_status(
        self,
        item_id: str,
        status: Literal["pending", "retried", "resolved", "abandoned"],
        error_message: str | None = None,
    ) -> DLQItem | None:
        item = self._items.get(item_id)
        if not item:
            return None
        updated = DLQItem(
            id=item.id,
            connector_id=item.connector_id,
            resource_id=item.resource_id,
            error_message=error_message or item.error_message,
            payload=item.payload,
            retry_count=item.retry_count + (1 if status == "retried" else 0),
            status=status,
            created_at=item.created_at,
            last_failed_at=datetime.now(UTC),
        )
        self._items[item.id] = updated
        logger.info("DLQ: Item %s status transitioned to %s", item_id, status)
        return updated

    async def delete_item(self, item_id: str) -> bool:
        if item_id in self._items:
            del self._items[item_id]
            logger.info("DLQ: Item %s purged", item_id)
            return True
        return False


class PgDLQAdapter(DLQPort):
    """PostgreSQL-backed Dead-Letter Queue adapter for production deployments."""

    def __init__(self, db_pool: Any | None = None, table_name: str = "aegismind_dlq") -> None:
        self.db_pool = db_pool
        self.table_name = table_name
        self._fallback = MemoryDLQAdapter()

    async def enqueue(
        self,
        connector_id: str,
        resource_id: str,
        error_message: str,
        payload: dict[str, Any] | None = None,
    ) -> DLQItem:
        if self.db_pool is not None:
            import json
            import uuid

            item_id = str(uuid.uuid4())
            now = datetime.now(UTC)
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    f"INSERT INTO {self.table_name} "  # noqa: S608
                    "(id, connector_id, resource_id, error_message, payload, "
                    "retry_count, status, created_at, last_failed_at) "
                    "VALUES ($1, $2, $3, $4, $5, 0, 'pending', $6, $6)",
                    item_id,
                    connector_id,
                    resource_id,
                    error_message,
                    json.dumps(payload or {}),
                    now,
                )
            return DLQItem(
                id=item_id,
                connector_id=connector_id,
                resource_id=resource_id,
                error_message=error_message,
                payload=payload or {},
                created_at=now,
                last_failed_at=now,
            )
        return await self._fallback.enqueue(connector_id, resource_id, error_message, payload)

    async def list_items(
        self,
        connector_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[DLQItem]:
        if self.db_pool is not None:
            import json

            query = (
                f"SELECT id, connector_id, resource_id, error_message, payload, "  # noqa: S608
                f"retry_count, status, created_at, last_failed_at "
                f"FROM {self.table_name} WHERE 1=1"
            )
            params: list[Any] = []
            idx = 1
            if connector_id:
                query += f" AND connector_id = ${idx}"
                params.append(connector_id)
                idx += 1
            if status:
                query += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            query += f" ORDER BY last_failed_at DESC LIMIT ${idx}"
            params.append(limit)

            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                items = []
                for r in rows:
                    raw_payload = r["payload"]
                    parsed_payload = (
                        json.loads(raw_payload)
                        if isinstance(raw_payload, str)
                        else dict(raw_payload or {})
                    )
                    items.append(
                        DLQItem(
                            id=r["id"],
                            connector_id=r["connector_id"],
                            resource_id=r["resource_id"],
                            error_message=r["error_message"],
                            payload=parsed_payload,
                            retry_count=r["retry_count"],
                            status=r["status"],
                            created_at=r["created_at"],
                            last_failed_at=r["last_failed_at"],
                        )
                    )
                return items
        return await self._fallback.list_items(connector_id, status, limit)

    async def get_item(self, item_id: str) -> DLQItem | None:
        if self.db_pool is not None:
            import json

            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT id, connector_id, resource_id, error_message, payload, "  # noqa: S608
                    f"retry_count, status, created_at, last_failed_at "
                    f"FROM {self.table_name} WHERE id = $1",
                    item_id,
                )
                if not row:
                    return None
                raw_payload = row["payload"]
                parsed_payload = (
                    json.loads(raw_payload)
                    if isinstance(raw_payload, str)
                    else dict(raw_payload or {})
                )
                return DLQItem(
                    id=row["id"],
                    connector_id=row["connector_id"],
                    resource_id=row["resource_id"],
                    error_message=row["error_message"],
                    payload=parsed_payload,
                    retry_count=row["retry_count"],
                    status=row["status"],
                    created_at=row["created_at"],
                    last_failed_at=row["last_failed_at"],
                )
        return await self._fallback.get_item(item_id)

    async def update_status(
        self,
        item_id: str,
        status: Literal["pending", "retried", "resolved", "abandoned"],
        error_message: str | None = None,
    ) -> DLQItem | None:
        if self.db_pool is not None:
            now = datetime.now(UTC)
            async with self.db_pool.acquire() as conn:
                retry_inc = 1 if status == "retried" else 0
                if error_message:
                    await conn.execute(
                        f"UPDATE {self.table_name} SET status = $1, error_message = $2, "  # noqa: S608
                        f"retry_count = retry_count + $3, last_failed_at = $4 WHERE id = $5",
                        status,
                        error_message,
                        retry_inc,
                        now,
                        item_id,
                    )
                else:
                    await conn.execute(
                        f"UPDATE {self.table_name} SET status = $1, "  # noqa: S608
                        f"retry_count = retry_count + $2, last_failed_at = $3 WHERE id = $4",
                        status,
                        retry_inc,
                        now,
                        item_id,
                    )
            return await self.get_item(item_id)
        return await self._fallback.update_status(item_id, status, error_message)

    async def delete_item(self, item_id: str) -> bool:
        if self.db_pool is not None:
            async with self.db_pool.acquire() as conn:
                res = await conn.execute(
                    f"DELETE FROM {self.table_name} WHERE id = $1",  # noqa: S608
                    item_id,
                )
                return "DELETE 1" in res
        return await self._fallback.delete_item(item_id)
