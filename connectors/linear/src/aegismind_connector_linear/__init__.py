from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_linear.connector import LinearConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for linear connector."""
    return LinearConnector(config=config)


__all__ = [
    "LinearConnector",
    "get_connector",
]
