from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aegismind_types import (
    ACL,
    Chunk,
    Citation,
    Document,
    Filter,
    Permission,
    Principal,
    Record,
    SearchResult,
    TokenConsistency,
)
from pydantic import ValidationError


def test_principal_serialization_round_trip() -> None:
    principal = Principal(
        id="usr_123",
        type="user",
        tenant_id="tenant_acme",
        attributes={"department": "security", "clearance": "level_3"},
    )
    json_str = principal.model_dump_json()
    restored = Principal.model_validate_json(json_str)
    assert restored == principal


def test_principal_immutability() -> None:
    principal = Principal(id="usr_123", type="user")
    with pytest.raises(ValidationError):
        principal.id = "usr_456"  # type: ignore[misc]


def test_permission_serialization_and_immutability() -> None:
    perm = Permission(
        resource="document:doc_999",
        relation="viewer",
        subject="user:alice",
    )
    json_str = perm.model_dump_json()
    restored = Permission.model_validate_json(json_str)
    assert restored == perm

    with pytest.raises(ValidationError):
        perm.relation = "editor"  # type: ignore[misc]


def test_acl_serialization_and_immutability() -> None:
    acl = ACL(
        allowed_principals=["user:alice", "group:engineers"],
        denied_principals=["user:mallory"],
        is_public=False,
    )
    json_str = acl.model_dump_json()
    restored = ACL.model_validate_json(json_str)
    assert restored == acl

    with pytest.raises(ValidationError):
        acl.is_public = True  # type: ignore[misc]


def test_record_serialization_round_trip() -> None:
    now = datetime(2026, 9, 24, 7, 0, 0, tzinfo=UTC)
    record = Record(
        id="rec_1",
        source="confluence",
        external_id="conf_page_42",
        payload={"title": "Q3 Architecture", "body": "Microservices design"},
        acl=ACL(allowed_principals=["group:engineering"]),
        created_at=now,
        updated_at=now,
    )
    json_str = record.model_dump_json()
    restored = Record.model_validate_json(json_str)
    assert restored == record

    with pytest.raises(ValidationError):
        record.source = "google_drive"  # type: ignore[misc]


def test_document_serialization_round_trip() -> None:
    doc = Document(
        id="doc_42",
        uri="s3://aegismind-vault/docs/arch.pdf",
        title="Engineering Design Doc",
        mime_type="application/pdf",
        content="Clean hexagonal architecture with Ports and Adapters.",
        metadata={"author": "lead_architect", "version": 2},
        acl=ACL(allowed_principals=["user:alice"], is_public=False),
        tenant_id="tenant_primary",
    )
    json_str = doc.model_dump_json()
    restored = Document.model_validate_json(json_str)
    assert restored == doc

    with pytest.raises(ValidationError):
        doc.title = "Altered Title"  # type: ignore[misc]


def test_chunk_serialization_and_sparse_embedding() -> None:
    chunk = Chunk(
        id="chk_001",
        document_id="doc_42",
        index=0,
        content="Clean hexagonal architecture overview.",
        contextual_prefix="Document: Engineering Design Doc > Section 1",
        embedding=[0.12, 0.45, 0.78],
        sparse_embedding={1024: 0.85, 2048: 0.92},
        acl=ACL(is_public=True),
        metadata={"tokens": 8},
    )
    json_str = chunk.model_dump_json()
    restored = Chunk.model_validate_json(json_str)
    assert restored == chunk

    with pytest.raises(ValidationError):
        chunk.content = "New text"  # type: ignore[misc]


def test_citation_and_search_result_round_trip() -> None:
    citation = Citation(
        chunk_id="chk_001",
        document_id="doc_42",
        title="Engineering Design Doc",
        uri="s3://aegismind-vault/docs/arch.pdf",
        snippet="Clean hexagonal architecture overview.",
        score=0.985,
    )
    result = SearchResult(
        chunk_id="chk_001",
        document_id="doc_42",
        title="Engineering Design Doc",
        uri="s3://aegismind-vault/docs/arch.pdf",
        text="Clean hexagonal architecture overview.",
        score=0.985,
        citation=citation,
    )
    json_str = result.model_dump_json()
    restored = SearchResult.model_validate_json(json_str)
    assert restored == result

    with pytest.raises(ValidationError):
        result.score = 1.0  # type: ignore[misc]


def test_token_consistency_round_trip() -> None:
    consistency = TokenConsistency(
        token="zed_token_abcdef123456",
        at_least_as_fresh=True,
    )
    json_str = consistency.model_dump_json()
    restored = TokenConsistency.model_validate_json(json_str)
    assert restored == consistency

    with pytest.raises(ValidationError):
        consistency.at_least_as_fresh = False  # type: ignore[misc]


def test_filter_round_trip() -> None:
    search_filter = Filter(
        tenant_id="tenant_acme",
        groups=["eng_all", "sec_team"],
        custom_fields={"classification": "confidential", "year": 2026},
    )
    json_str = search_filter.model_dump_json()
    restored = Filter.model_validate_json(json_str)
    assert restored == search_filter

    with pytest.raises(ValidationError):
        search_filter.tenant_id = "tenant_other"  # type: ignore[misc]
