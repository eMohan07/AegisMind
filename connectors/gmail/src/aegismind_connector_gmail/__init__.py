from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_gmail.connector import GmailConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for gmail connector."""
    return GmailConnector(config=config)


__all__ = [
    "GmailConnector",
    "get_connector",
]
