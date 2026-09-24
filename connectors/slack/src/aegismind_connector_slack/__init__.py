from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_slack.connector import SlackConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for slack connector."""
    return SlackConnector(config=config)


__all__ = [
    "SlackConnector",
    "get_connector",
]
