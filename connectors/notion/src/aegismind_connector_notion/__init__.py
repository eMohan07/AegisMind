from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_notion.connector import NotionConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for notion connector."""
    return NotionConnector(config=config)


__all__ = [
    "NotionConnector",
    "get_connector",
]
