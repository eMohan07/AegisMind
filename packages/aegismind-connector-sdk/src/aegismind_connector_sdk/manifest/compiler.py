from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from aegismind_types import ACL, Record
from jsonpath_ng import parse as parse_jsonpath

from aegismind_connector_sdk.manifest.schema import ManifestSpec
from aegismind_connector_sdk.ports import ConnectorPort, ConnectorSpec

logger = logging.getLogger(__name__)


def _extract_values(jsonpath_expr: str, data: Any) -> list[Any]:
    """Extract values from dictionary or list using JSONPath with fallback."""
    if not jsonpath_expr:
        return []

    # Fast path for direct dictionary keys
    if isinstance(data, dict) and jsonpath_expr in data:
        val = data[jsonpath_expr]
        return val if isinstance(val, list) else [val]

    try:
        expr = parse_jsonpath(jsonpath_expr)
        matches = expr.find(data)
        values = []
        for m in matches:
            if isinstance(m.value, list):
                values.extend(m.value)
            else:
                values.append(m.value)
        return values
    except Exception as exc:
        logger.debug("JSONPath evaluation '%s' returned empty: %s", jsonpath_expr, exc)
        return []


def _extract_first(jsonpath_expr: str, data: Any, default: Any = None) -> Any:
    """Extract first value matching JSONPath or return default."""
    vals = _extract_values(jsonpath_expr, data)
    return vals[0] if vals else default


class CompiledManifestConnector(ConnectorPort):
    """Runnable connector compiled from a declarative ManifestSpec."""

    def __init__(
        self,
        manifest: ManifestSpec,
        config: dict[str, Any] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.manifest = manifest
        self.config = config or {}
        self._client = client

    def spec(self) -> ConnectorSpec:
        return ConnectorSpec(
            name=self.manifest.name,
            version=self.manifest.version,
            documentation_url=None,
            config_schema={},
            supports_incremental=self.manifest.cursor is not None,
            supported_destination_sync_modes=["full_refresh", "incremental"]
            if self.manifest.cursor
            else ["full_refresh"],
        )

    def _get_auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        auth = self.manifest.auth

        if auth.type == "bearer":
            token = auth.token or self.config.get("token", "")
            headers["Authorization"] = f"Bearer {token}"
        elif auth.type == "api_key":
            token = auth.token or self.config.get("api_key", "")
            headers[auth.header_name] = token
        elif auth.type == "basic":
            import base64

            username = auth.username or self.config.get("username", "")
            password = auth.password or self.config.get("password", "")
            b64 = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {b64}"

        return headers

    async def check(self) -> bool:
        """Verify endpoint connectivity."""
        headers = self._get_auth_headers()
        headers.update(self.manifest.endpoint.headers)
        path = self.manifest.endpoint.path.lstrip("/")
        base = self.manifest.base_url.rstrip("/")
        target_url = f"{base}/{path}"

        client_created = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient()
            client_created = True

        try:
            resp = await client.request(
                method="GET",
                url=target_url,
                headers=headers,
                params=self.manifest.endpoint.params,
                timeout=10.0,
            )
            return resp.status_code < 500
        except Exception as exc:
            logger.warning("Connectivity check failed for %s: %s", self.manifest.name, exc)
            return False
        finally:
            if client_created:
                await client.aclose()

    async def read(
        self,
        state: dict[str, Any] | None = None,
    ) -> AsyncIterator[Record]:
        state_dict = dict(state) if state else {}
        cursor_val = (
            state_dict.get(self.manifest.cursor.state_field, self.manifest.cursor.initial_value)
            if self.manifest.cursor
            else None
        )

        headers = self._get_auth_headers()
        headers.update(self.manifest.endpoint.headers)
        base_url = f"{self.manifest.base_url.rstrip('/')}/{self.manifest.endpoint.path.lstrip('/')}"

        client_created = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient()
            client_created = True

        pagination = self.manifest.pagination
        current_page = 1
        current_offset = 0
        current_cursor = cursor_val

        try:
            while True:
                params = dict(self.manifest.endpoint.params)

                # Inject pagination parameters
                if pagination.type == "cursor":
                    if current_cursor:
                        params[pagination.cursor_param] = str(current_cursor)
                    params["limit"] = str(pagination.page_size)
                elif pagination.type == "page_number":
                    params[pagination.page_param] = str(current_page)
                    params[pagination.limit_param] = str(pagination.page_size)
                elif pagination.type == "offset":
                    params[pagination.offset_param] = str(current_offset)
                    params[pagination.limit_param] = str(pagination.page_size)

                # Inject cursor into params if incremental sync specified
                if self.manifest.cursor and current_cursor:
                    params[self.manifest.cursor.cursor_field] = str(current_cursor)

                response = await client.request(
                    method=self.manifest.endpoint.method,
                    url=base_url,
                    headers=headers,
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                payload = response.json()

                # Extract records
                records_raw = _extract_values(self.manifest.endpoint.records_path, payload)
                if not records_raw:
                    break

                for item in records_raw:
                    if not isinstance(item, dict):
                        continue

                    # Extract record id and external_id
                    rec_id = str(_extract_first(self.manifest.id_path, item, default="unknown_id"))
                    ext_id = str(
                        _extract_first(self.manifest.external_id_path, item, default=rec_id)
                    )

                    # Extract ACL
                    acl_spec = self.manifest.acl_mapping
                    allowed = list(acl_spec.static_allowed)
                    if acl_spec.allowed_principals_path:
                        extracted_allowed = _extract_values(acl_spec.allowed_principals_path, item)
                        allowed.extend(str(a) for a in extracted_allowed)

                    denied: list[str] = []
                    if acl_spec.denied_principals_path:
                        extracted_denied = _extract_values(acl_spec.denied_principals_path, item)
                        denied.extend(str(d) for d in extracted_denied)

                    is_public = acl_spec.default_public
                    if acl_spec.is_public_path:
                        extracted_pub = _extract_first(acl_spec.is_public_path, item)
                        if extracted_pub is not None:
                            is_public = bool(extracted_pub)

                    record_acl = ACL(
                        allowed_principals=allowed,
                        denied_principals=denied,
                        is_public=is_public,
                    )

                    # Track updated cursor
                    if self.manifest.cursor:
                        new_cursor = _extract_first(self.manifest.cursor.cursor_field, item)
                        if new_cursor is not None:
                            state_dict[self.manifest.cursor.state_field] = new_cursor

                    yield Record(
                        id=rec_id,
                        source=self.manifest.name,
                        external_id=ext_id,
                        payload=item,
                        acl=record_acl,
                    )

                # Determine next page / break condition
                if pagination.type == "none":
                    break
                elif pagination.type == "page_number":
                    if len(records_raw) < pagination.page_size:
                        break
                    current_page += 1
                elif pagination.type == "offset":
                    if len(records_raw) < pagination.page_size:
                        break
                    current_offset += len(records_raw)
                elif pagination.type == "cursor":
                    next_cursor = None
                    if pagination.next_cursor_path:
                        next_cursor = _extract_first(pagination.next_cursor_path, payload)
                    if not next_cursor or next_cursor == current_cursor:
                        break
                    current_cursor = next_cursor

        finally:
            if client_created:
                await client.aclose()


def compile_manifest(
    manifest: ManifestSpec,
    config: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> ConnectorPort:
    """Compile a validated ManifestSpec into a runnable ConnectorPort instance."""
    return CompiledManifestConnector(manifest=manifest, config=config, client=client)
