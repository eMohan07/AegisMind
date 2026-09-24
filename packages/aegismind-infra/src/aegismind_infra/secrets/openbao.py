from __future__ import annotations

import logging
from typing import Any

import httpx

from aegismind_infra.ports import SecretStorePort

logger = logging.getLogger(__name__)


class OpenBaoSecretStore(SecretStorePort):
    """Secret store adapter communicating with OpenBao / HashiCorp Vault KV v2 API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8200",
        token: str = "",
        mount_path: str = "secret",
        namespace: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.mount_path = mount_path.strip("/")
        self.namespace = namespace
        self._client = client

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "X-Vault-Token": self.token,
            "X-Bao-Token": self.token,
            "Content-Type": "application/json",
        }
        if self.namespace:
            headers["X-Vault-Namespace"] = self.namespace
        return headers

    def _build_path(self, key: str, tenant_id: str | None) -> str:
        clean_key = key.strip("/")
        if tenant_id:
            return f"{tenant_id.strip('/')}/{clean_key}"
        return clean_key

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self.base_url}/v1/{self.mount_path}/{path}"
        headers = self._get_headers()
        if self._client is not None:
            return await self._client.request(method, url, headers=headers, json=json_data)
        async with httpx.AsyncClient() as client:
            return await client.request(method, url, headers=headers, json=json_data)

    async def get_secret(self, key: str, tenant_id: str | None = None) -> str | None:
        """Fetch secret from OpenBao KV v2."""
        subpath = self._build_path(key, tenant_id)
        path = f"data/{subpath}"
        try:
            resp = await self._request("GET", path)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data", {}).get("data", {})
            value = data.get("value")
            return str(value) if value is not None else None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            logger.error("OpenBao error reading secret '%s': %s", key, exc)
            raise

    async def set_secret(self, key: str, value: str, tenant_id: str | None = None) -> None:
        """Write secret to OpenBao KV v2."""
        subpath = self._build_path(key, tenant_id)
        path = f"data/{subpath}"
        payload = {"data": {"value": value}}
        resp = await self._request("POST", path, json_data=payload)
        resp.raise_for_status()

    async def delete_secret(self, key: str, tenant_id: str | None = None) -> bool:
        """Delete secret metadata from OpenBao KV v2."""
        subpath = self._build_path(key, tenant_id)
        path = f"metadata/{subpath}"
        try:
            resp = await self._request("DELETE", path)
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return False
            logger.error("OpenBao error deleting secret '%s': %s", key, exc)
            raise
