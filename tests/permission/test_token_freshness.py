from __future__ import annotations

import pytest
from aegismind_authz.ports import AuthzPort, CheckRequest, RelationshipTuple
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import Chunk, Principal, TokenConsistency


class FreshnessTrackingAuthz(AuthzPort):
    """Authz adapter that verifies consistency tokens and tracks evaluated revisions."""

    def __init__(self) -> None:
        self.recorded_consistencies: list[TokenConsistency | None] = []
        self._tuples: set[tuple[str, str, str]] = set()

    async def write_tuples(self, tuples: list[RelationshipTuple]) -> TokenConsistency:
        for t in tuples:
            self._tuples.add((t.resource, t.relation, t.subject))
        return TokenConsistency(token="zed_rev_100", at_least_as_fresh=True)

    async def delete_tuples(self, tuples: list[RelationshipTuple]) -> TokenConsistency:
        for t in tuples:
            self._tuples.discard((t.resource, t.relation, t.subject))
        return TokenConsistency(token="zed_rev_101", at_least_as_fresh=True)

    async def bulk_check(
        self,
        requests: list[CheckRequest],
        consistency: TokenConsistency | None = None,
    ) -> list[bool]:
        self.recorded_consistencies.append(consistency)
        results = []
        for req in requests:
            results.append((req.resource, req.permission, req.subject) in self._tuples)
        return results

    async def check_permission(self, subject: Principal, relation: str, resource: str) -> bool:
        return True


@pytest.mark.permission
@pytest.mark.asyncio
async def test_retrieval_honors_zanzibar_token_freshness() -> None:
    """Verify that retrieval strictly enforces at_least_as_fresh consistency tokens."""
    authz = FreshnessTrackingAuthz()
    vector_store = MemoryVectorStoreAdapter()
    embedder = MockEmbedderAdapter(dimension=8)
    reranker = MockRerankerAdapter()

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    # Ingest document chunk
    chunk = Chunk(
        id="chunk_fresh_1",
        document_id="doc_fresh",
        content="Distributed consensus log replication guidelines.",
        embedding=[0.1] * 8,
        metadata={"title": "Consensus Guide"},
    )
    await vector_store.upsert([chunk])

    # Write tuple and get fresh zed consistency token
    token = await authz.write_tuples(
        [
            RelationshipTuple(
                resource="document:doc_fresh",
                relation="viewer",
                subject="user:alice",
            )
        ]
    )
    assert token.token == "zed_rev_100"

    alice = Principal(id="alice", type="user")

    # 1. Execute retrieval with explicit fresh consistency token
    res = await pipeline.execute(
        query="consensus log replication",
        principal=alice,
        consistency=token,
    )
    assert len(res.results) == 1

    # Verify that authz.bulk_check received the consistency requirement
    assert len(authz.recorded_consistencies) > 0
    last_consistency = authz.recorded_consistencies[-1]
    assert last_consistency is not None
    assert last_consistency.token == "zed_rev_100"
    assert last_consistency.at_least_as_fresh is True

    # 2. Execute retrieval without passing explicit consistency:
    # Sacred pipeline MUST still enforce requirement="at_least_as_fresh"
    await pipeline.execute(
        query="consensus log replication",
        principal=alice,
        consistency=None,
    )
    default_consistency = authz.recorded_consistencies[-1]
    assert default_consistency is not None
    assert default_consistency.at_least_as_fresh is True
