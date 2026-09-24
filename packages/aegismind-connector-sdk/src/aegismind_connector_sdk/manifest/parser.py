from __future__ import annotations

import logging
from typing import Any

import yaml

from aegismind_connector_sdk.manifest.schema import ManifestSpec

logger = logging.getLogger(__name__)


def parse_manifest(raw_yaml_or_dict: str | dict[str, Any]) -> ManifestSpec:
    """Parse and validate a declarative connector manifest specification.

    Args:
        raw_yaml_or_dict: YAML string or Python dictionary representing manifest.

    Returns:
        Validated ManifestSpec instance.

    Raises:
        ValueError: If input cannot be parsed or fails schema validation.
    """
    if isinstance(raw_yaml_or_dict, str):
        try:
            data = yaml.safe_load(raw_yaml_or_dict)
        except Exception as exc:
            logger.error("Failed to parse YAML manifest: %s", exc)
            raise ValueError(f"Invalid YAML manifest syntax: {exc}") from exc
    elif isinstance(raw_yaml_or_dict, dict):
        data = raw_yaml_or_dict
    else:
        raise ValueError("Manifest input must be a YAML string or dictionary")

    if not isinstance(data, dict):
        raise ValueError("Manifest root structure must be a mapping dictionary")

    try:
        return ManifestSpec.model_validate(data)
    except Exception as exc:
        logger.error("Manifest schema validation failed: %s", exc)
        raise ValueError(f"Manifest schema validation error: {exc}") from exc
