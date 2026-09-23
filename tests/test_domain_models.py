from __future__ import annotations

import pytest
from pydantic import ValidationError

from aegismind_core.domain.models import (
    Chunk,
    RetrievalQuery,
    ScoredChunk,
)
from aegismind_core.domain.permissions import (
    ConsistencyRequirement,
    ConsistencyToken,
    Resource,
    Subject,
)


def test_subject_and_resource_serialization() -> None:
    subject_user = Subject(type="user", id="alice")
    assert subject_user.to_string() == "user:alice"

    subject_group = Subject(type="group", id="engineers", relation="member")
    assert subject_group.to_string() == "group:engineers#member"

    res_doc = Resource(type="document", id="doc_1")
    assert res_doc.to_string() == "document:doc_1"


def test_consistency_token_defaults() -> None:
    token = ConsistencyToken()
    assert token.requirement == ConsistencyRequirement.AT_LEAST_AS_FRESH
    assert token.token is None


def test_retrieval_query_overfetch_validation() -> None:
    # Valid bounds: 3.0 to 5.0
    query = RetrievalQuery(
        query_text="quarterly roadmap",
        user_id="alice",
        top_k=5,
        overfetch_factor=4.5,
    )
    assert query.overfetch_factor == 4.5

    # Out of range low
    with pytest.raises(ValidationError):
        RetrievalQuery(
            query_text="invalid query",
            user_id="alice",
            top_k=5,
            overfetch_factor=2.0,
        )

    # Out of range high
    with pytest.raises(ValidationError):
        RetrievalQuery(
            query_text="invalid query",
            user_id="alice",
            top_k=5,
            overfetch_factor=6.0,
        )


def test_chunk_and_scored_chunk() -> None:
    chunk = Chunk(
        id="c1",
        document_id="d1",
        content="Confidential project details",
        chunk_index=0,
        embedding=[0.1, 0.2, 0.3],
    )
    scored = ScoredChunk(chunk=chunk, score=0.89)
    assert scored.score == 0.89
    assert scored.chunk.document_id == "d1"
