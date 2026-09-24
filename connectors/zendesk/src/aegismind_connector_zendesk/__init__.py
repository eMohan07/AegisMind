from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_zendesk.connector import ZendeskConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for zendesk connector."""
    return ZendeskConnector(config=config)


__all__ = [
    "ZendeskConnector",
    "get_connector",
]
