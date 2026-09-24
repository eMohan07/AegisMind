from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_weblink.connector import WeblinkConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for weblink connector."""
    return WeblinkConnector(config=config)


__all__ = [
    "WeblinkConnector",
    "get_connector",
]
