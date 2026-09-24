from __future__ import annotations

from typing import Any

from aegismind_connector_sdk.ports import ConnectorPort

from aegismind_connector_salesforce.connector import SalesforceConnector


def get_connector(config: dict[str, Any] | None = None) -> ConnectorPort:
    """Factory entry point for salesforce connector."""
    return SalesforceConnector(config=config)


__all__ = [
    "SalesforceConnector",
    "get_connector",
]
