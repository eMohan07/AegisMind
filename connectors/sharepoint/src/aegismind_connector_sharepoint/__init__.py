from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_sharepoint.connector import SharePointConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for sharepoint connector."""
    return SharePointConnector(config=config)


__all__ = [
    "SharePointConnector",
    "get_connector",
]
