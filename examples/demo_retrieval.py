from __future__ import annotations

import asyncio
import logging
import sys

from aegismind_core.domain.models import Chunk, RetrievalQuery
from aegismind_core.domain.permissions import (
    ConsistencyRequirement,
    ConsistencyToken,
    Resource,
    Subject,
)
from aegismind_core.ports.authz import AuthzPort
from aegismind_core.ports.vector_store import VectorStorePort
from aegismind_core.services.retrieval import RetrievalService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aegismind.demo")


async def main() -> None:
    logger.info("Initializing AegisMind RetrievalService via dynamic registry...")
    service = RetrievalService()

    authz: AuthzPort = service._authz
    vector_store: VectorStorePort = service._vector_store

    logger.info("Seeding knowledge corpus and document chunks...")
    corpus = [
        ("doc_eng_1", "Architecture Blueprint: Core Payment Engine", [0.95] * 16),
        ("doc_eng_2", "Database Migration: PostgreSQL Schema", [0.90] * 16),
        ("doc_hr_1", "Executive Compensation and Salary Bands", [0.94] * 16),
        ("doc_hr_2", "Employee Benefits and Health Insurance", [0.85] * 16),
        ("doc_pub_1", "General Employee Handbook and Code of Conduct", [0.88] * 16),
    ]

    chunks = [
        Chunk(
            id=f"chunk_{doc_id}",
            document_id=doc_id,
            content=title,
            chunk_index=0,
            embedding=emb,
        )
        for doc_id, title, emb in corpus
    ]
    await vector_store.upsert(chunks)

    logger.info("Configuring Zanzibar access control relationships...")
    # Alice is an Engineer
    alice = Subject(type="user", id="alice")
    await authz.write_relationship(alice, "reader", Resource(type="document", id="doc_eng_1"))
    await authz.write_relationship(alice, "reader", Resource(type="document", id="doc_eng_2"))

    # Bob is in HR
    bob = Subject(type="user", id="bob")
    await authz.write_relationship(bob, "reader", Resource(type="document", id="doc_hr_1"))
    await authz.write_relationship(bob, "reader", Resource(type="document", id="doc_hr_2"))

    # Public document has wildcard access
    wildcard_user = Subject(type="user", id="*")
    await authz.write_relationship(
        wildcard_user, "reader", Resource(type="document", id="doc_pub_1")
    )

    logger.info("Simulating multi-tenant permission-aware retrieval...")

    # Alice queries
    q_alice = RetrievalQuery(
        query_text="salary architecture policies",
        user_id="alice",
        top_k=5,
        overfetch_factor=3.0,
        consistency=ConsistencyToken(requirement=ConsistencyRequirement.AT_LEAST_AS_FRESH),
    )
    res_alice = await service.search(q_alice)
    logger.info("Results for Alice (Engineer):")
    for item in res_alice.chunks:
        logger.info(
            "  - [%.4f] Doc: %s, Text: %s",
            item.score,
            item.chunk.document_id,
            item.chunk.content,
        )
    logger.info(
        "Alice evaluation summary: total evaluated=%d, authorized retained=%d",
        res_alice.total_candidates_evaluated,
        res_alice.authorized_candidates_count,
    )

    # Bob queries
    q_bob = RetrievalQuery(
        query_text="salary architecture policies",
        user_id="bob",
        top_k=5,
        overfetch_factor=3.0,
        consistency=ConsistencyToken(requirement=ConsistencyRequirement.AT_LEAST_AS_FRESH),
    )
    res_bob = await service.search(q_bob)
    logger.info("Results for Bob (HR):")
    for item in res_bob.chunks:
        logger.info(
            "  - [%.4f] Doc: %s, Text: %s",
            item.score,
            item.chunk.document_id,
            item.chunk.content,
        )
    logger.info(
        "Bob evaluation summary: total evaluated=%d, authorized retained=%d",
        res_bob.total_candidates_evaluated,
        res_bob.authorized_candidates_count,
    )

    # Charlie (Guest) queries
    q_charlie = RetrievalQuery(
        query_text="salary architecture policies",
        user_id="charlie",
        top_k=5,
        overfetch_factor=3.0,
        consistency=ConsistencyToken(requirement=ConsistencyRequirement.AT_LEAST_AS_FRESH),
    )
    res_charlie = await service.search(q_charlie)
    logger.info("Results for Charlie (Guest):")
    for item in res_charlie.chunks:
        logger.info(
            "  - [%.4f] Doc: %s, Text: %s",
            item.score,
            item.chunk.document_id,
            item.chunk.content,
        )
    logger.info(
        "Charlie evaluation summary: total evaluated=%d, authorized retained=%d",
        res_charlie.total_candidates_evaluated,
        res_charlie.authorized_candidates_count,
    )


if __name__ == "__main__":
    asyncio.run(main())
