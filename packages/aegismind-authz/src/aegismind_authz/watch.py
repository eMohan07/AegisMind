from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from aegismind_types import TokenConsistency

from aegismind_authz.ports import RelationshipTuple

logger = logging.getLogger(__name__)


class SpiceDBWatcher:
    """SpiceDB Watch API stream subscriber for relationship mutation and cache invalidation.

    Monitors real-time Zanzibar tuple writes and deletions to immediately invalidate any
    downstream query or permission caches.
    """

    def __init__(
        self,
        endpoint: str = "localhost:50051",
        token: str = "aegismind_preshared_key",  # noqa: S107
        client: Any | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.token = token
        self._client = client
        self._invalidation_callbacks: list[Callable[[RelationshipTuple, str], None]] = []
        self._stop_event = asyncio.Event()

    def register_invalidation_callback(
        self,
        callback: Callable[[RelationshipTuple, str], None],
    ) -> None:
        """Register a callback triggered on tuple deletion or modification."""
        self._invalidation_callbacks.append(callback)

    async def watch_mutations(
        self,
        start_cursor: TokenConsistency | None = None,
    ) -> AsyncIterator[tuple[RelationshipTuple, str]]:
        """Stream relationship tuple mutations (TOUCH or DELETE) from SpiceDB.

        Yields (RelationshipTuple, operation) pairs where operation is 'TOUCH' or 'DELETE'.
        """
        self._stop_event.clear()
        logger.info("Started SpiceDB Watch API stream subscriber targeting %s", self.endpoint)

        if self._client is None:
            # In offline or mock environment, wait until stopped
            try:
                await self._stop_event.wait()
            except asyncio.CancelledError:
                pass
            return

        try:
            from authzed.api.v1 import WatchRequest, ZedToken

            cursor_token = (
                ZedToken(token=start_cursor.token) if start_cursor and start_cursor.token else None
            )
            req = WatchRequest(optional_start_cursor=cursor_token)

            for response in self._client.Watch(req):
                if self._stop_event.is_set():
                    break
                for update in response.updates:
                    rel = update.relationship
                    op = "DELETE" if update.operation == 2 else "TOUCH"
                    resource_str = f"{rel.resource.object_type}:{rel.resource.object_id}"
                    subject_str = f"{rel.subject.object.object_type}:{rel.subject.object.object_id}"
                    tuple_entry = RelationshipTuple(
                        resource=resource_str,
                        relation=rel.relation,
                        subject=subject_str,
                    )

                    # Trigger any registered cache invalidation callbacks
                    for cb in self._invalidation_callbacks:
                        try:
                            cb(tuple_entry, op)
                        except Exception as exc:
                            logger.error("Error executing cache invalidation callback: %s", exc)

                    yield tuple_entry, op
        except Exception as exc:
            logger.warning("SpiceDB Watch stream disconnected: %s", exc)
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop watching mutations."""
        self._running = False
