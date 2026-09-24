from __future__ import annotations

import httpx
import pytest
from aegismind_connector_sdk.manifest.compiler import compile_manifest
from aegismind_connector_sdk.manifest.parser import parse_manifest

SAMPLE_YAML_MANIFEST = """
name: sample_wiki
version: 1.0.0
description: Sample declarative documentation connector
base_url: https://api.samplewiki.local/v1
endpoint:
  path: /pages
  method: GET
  params:
    space: engineering
  records_path: items
auth:
  type: bearer
  token: secret_token_xyz
pagination:
  type: cursor
  page_size: 2
  cursor_param: next_page
  next_cursor_path: cursor.next
cursor:
  cursor_field: modified_at
  state_field: last_modified
acl_mapping:
  allowed_principals_path: permissions.allowed
  is_public_path: is_public
  default_public: false
id_path: page_id
external_id_path: external_key
"""


def test_parse_manifest_valid() -> None:
    manifest = parse_manifest(SAMPLE_YAML_MANIFEST)
    assert manifest.name == "sample_wiki"
    assert manifest.version == "1.0.0"
    assert manifest.endpoint.path == "/pages"
    assert manifest.pagination.type == "cursor"
    assert manifest.cursor is not None
    assert manifest.cursor.cursor_field == "modified_at"
    assert manifest.acl_mapping.allowed_principals_path == "permissions.allowed"


def test_parse_manifest_invalid_syntax() -> None:
    with pytest.raises(ValueError):
        parse_manifest("invalid: yaml: [broken")


@pytest.mark.asyncio
async def test_compiled_connector_execution() -> None:
    manifest = parse_manifest(SAMPLE_YAML_MANIFEST)

    # Mock HTTP handler returning 2 pages
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        assert request.headers.get("Authorization") == "Bearer secret_token_xyz"

        if "next_page=cursor_2" in url_str:
            # Page 2
            data = {
                "items": [
                    {
                        "page_id": "page_3",
                        "external_key": "wiki_p3",
                        "title": "Onboarding Guide",
                        "modified_at": "2026-09-24T05:00:00Z",
                        "is_public": True,
                        "permissions": {"allowed": ["group:all_company"]},
                    }
                ],
                "cursor": {"next": None},
            }
        else:
            # Page 1
            data = {
                "items": [
                    {
                        "page_id": "page_1",
                        "external_key": "wiki_p1",
                        "title": "Architecture Spec",
                        "modified_at": "2026-09-24T01:00:00Z",
                        "is_public": False,
                        "permissions": {"allowed": ["user:alice", "user:bob"]},
                    },
                    {
                        "page_id": "page_2",
                        "external_key": "wiki_p2",
                        "title": "Security Guidelines",
                        "modified_at": "2026-09-24T02:00:00Z",
                        "is_public": False,
                        "permissions": {"allowed": ["group:sec#member"]},
                    },
                ],
                "cursor": {"next": "cursor_2"},
            }

        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        connector = compile_manifest(manifest=manifest, client=client)

        spec = connector.spec()
        assert spec.name == "sample_wiki"
        assert spec.supports_incremental is True

        is_healthy = await connector.check()
        assert is_healthy is True

        # Read records across both pages
        records = [r async for r in connector.read()]
        assert len(records) == 3

        # Record 1 checks
        r1 = records[0]
        assert r1.id == "page_1"
        assert r1.external_id == "wiki_p1"
        assert r1.source == "sample_wiki"
        assert not r1.acl.is_public
        assert "user:alice" in r1.acl.allowed_principals

        # Record 3 checks (public page)
        r3 = records[2]
        assert r3.id == "page_3"
        assert r3.acl.is_public is True
        assert "group:all_company" in r3.acl.allowed_principals
