from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_google_drive.connector import GoogleDriveConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for google_drive connector."""
    return GoogleDriveConnector(config=config)


__all__ = [
    "GoogleDriveConnector",
    "get_connector",
]
