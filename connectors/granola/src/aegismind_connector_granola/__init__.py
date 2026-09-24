from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_granola.connector import GranolaConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for granola connector."""
    return GranolaConnector(config=config)


__all__ = [
    "GranolaConnector",
    "get_connector",
]
