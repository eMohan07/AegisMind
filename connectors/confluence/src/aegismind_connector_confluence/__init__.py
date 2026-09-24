from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_confluence.connector import ConfluenceConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for confluence connector."""
    return ConfluenceConnector(config=config)


__all__ = [
    "ConfluenceConnector",
    "get_connector",
]
