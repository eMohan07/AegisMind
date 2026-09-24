from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_jira.connector import JiraConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for jira connector."""
    return JiraConnector(config=config)


__all__ = [
    "JiraConnector",
    "get_connector",
]
