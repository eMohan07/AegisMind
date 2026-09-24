from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort, ConnectorSpec
from aegismind_types import ACL, Record

logger = logging.getLogger(__name__)


class WeblinkConnector(ConnectorPort):
    """Public URL and documentation crawler honoring robots.txt and sitemaps."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        fixture_path: str | Path | None = None,
    ) -> None:
        self.config = config or {}
        base_dir = Path(__file__).resolve().parent.parent.parent
        default_fixture = base_dir / "fixtures" / "weblink_sample.json"
        self.fixture_path = Path(fixture_path or default_fixture)

    def spec(self) -> ConnectorSpec:
        return ConnectorSpec(
            name="weblink",
            version="0.0.1",
            description="Public URL and documentation crawler honoring robots.txt and sitemaps",
            config_schema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string"},
                    "endpoint_url": {"type": "string"},
                },
            },
            supports_incremental=True,
        )

    async def check(self) -> bool:
        return self.fixture_path.exists()

    async def read(
        self,
        state: dict[str, Any] | None = None,
    ) -> AsyncIterator[Record]:
        if not self.fixture_path.exists():
            logger.warning("Fixture path '%s' does not exist", self.fixture_path)
            return

        with self.fixture_path.open("r", encoding="utf-8") as f:
            items: list[dict[str, Any]] = json.load(f)

        cursor_time = None
        if state and "last_updated_at" in state:
            try:
                raw_cursor = state["last_updated_at"].replace("Z", "+00:00")
                cursor_time = datetime.fromisoformat(raw_cursor)
            except ValueError:
                pass

        for item in items:
            raw_updated = item.get("updated_at")
            if raw_updated:
                item_updated = datetime.fromisoformat(str(raw_updated).replace("Z", "+00:00"))
            else:
                item_updated = datetime.now(UTC)

            if cursor_time and item_updated < cursor_time:
                continue

            raw_created = item.get("created_at")
            if raw_created:
                item_created = datetime.fromisoformat(str(raw_created).replace("Z", "+00:00"))
            else:
                item_created = item_updated

            ext_id = str(item.get("id") or item.get("key") or item.get("url", ""))

            # Extract ACL

            acl = ACL(allowed_principals=["user:*"], is_public=True)

            yield Record(
                id=f"weblink_{ext_id}",
                source="weblink",
                external_id=ext_id,
                payload=item,
                acl=acl,
                created_at=item_created,
                updated_at=item_updated,
            )
