from __future__ import annotations

import logging
from typing import Any

from aegismind_authz.adapters.memory import MemoryAuthzAdapter
from aegismind_authz.ports import RelationshipTuple
from aegismind_retrieval.adapters_model import MockEmbedderAdapter, MockRerankerAdapter
from aegismind_retrieval.adapters_vector import MemoryVectorStoreAdapter
from aegismind_retrieval.pipeline import RetrievalPipeline
from aegismind_types import ACL, Chunk

from aegismind_core.registry import list_adapters, resolve_adapter
from aegismind_core.routes import CoreState

logger = logging.getLogger(__name__)

# Sample enterprise knowledge documents for initial corpus
INITIAL_DOCUMENTS: list[dict[str, Any]] = [
    {
        "id": "doc-arch-01",
        "title": "AegisMind System Architecture and Zero-Leakage Guarantee",
        "uri": "https://wiki.corp.internal/architecture/zero-leakage",
        "tenant_id": "corp-default",
        "content": (
            "AegisMind enforces a strict zero-leakage security model for enterprise search "
            "and generative AI. All retrieval queries pass through Zanzibar-compatible "
            "authorization checks before candidate chunks reach the reranker or answer "
            "synthesis stages. Even if an unauthorized document shares high semantic similarity "
            "with a user query, Zanzibar evaluation discards the candidate chunks at retrieval "
            "time, eliminating vector-space authorization leakage entirely."
        ),
        "allowed_users": ["alice", "bob", "charlie", "anonymous"],
    },
    {
        "id": "doc-sec-02",
        "title": "SEC-892: Zero Stale Read Revocation Policy",
        "uri": "https://jira.corp.internal/browse/SEC-892",
        "tenant_id": "corp-default",
        "content": (
            "Under ticket SEC-892, AegisMind guarantees a zero stale read window for permission "
            "revocations. When a user's viewer permission is deleted or revoked in Zanzibar "
            "(SpiceDB), all subsequent read and search queries immediately enforce the updated "
            "authorization state. Consistency requirements use at_least_as_fresh with revision "
            "tokens, preventing any caching layer from returning stale unauthorized documents."
        ),
        "allowed_users": ["alice", "bob"],
    },
    {
        "id": "doc-pipe-03",
        "title": "The 7-Stage Sacred Enforcement Pipeline",
        "uri": "https://wiki.corp.internal/retrieval/sacred-pipeline",
        "tenant_id": "corp-default",
        "content": (
            "AegisMind's Sacred Enforcement Pipeline coordinates the 7-stage retrieval lifecycle: "
            "Stage 1: Embed query into dense and sparse representations. "
            "Stage 2: Coarse pre-filter by tenant and group boundary. "
            "Stage 3: Overfetch candidate chunks by an overfetch factor of 3.0 to 5.0. "
            "Stage 4: Perform bulk authorization checks against Zanzibar with at_least_as_fresh "
            "consistency. "
            "Stage 5: Drop denied candidates strictly. "
            "Stage 6: Rerank surviving candidates with cross-encoder models. "
            "Stage 7: Attach verifiable deep-linked citations to every answer."
        ),
        "allowed_users": ["alice", "bob", "charlie", "anonymous"],
    },
    {
        "id": "doc-enc-04",
        "title": "Envelope Encryption and KMS Key Hierarchy",
        "uri": "https://wiki.corp.internal/security/envelope-encryption",
        "tenant_id": "corp-default",
        "content": (
            "Data stored in AegisMind is secured using AES-256-GCM envelope encryption. "
            "Document encryption keys (DEKs) are generated per document and encrypted under "
            "a root Key Encryption Key (KEK) managed in KMS or local master key storage. "
            "Vector embeddings and chunk content in PostgreSQL pgvectorscale remain "
            "cryptographically protected at rest and during transit."
        ),
        "allowed_users": ["alice", "bob"],
    },
    {
        "id": "doc-conn-05",
        "title": "Enterprise Connectors and Cursor-Based Sync",
        "uri": "https://wiki.corp.internal/connectors/overview",
        "tenant_id": "corp-default",
        "content": (
            "AegisMind connects to 15 enterprise sources including Confluence, Jira, Google Drive, "
            "Slack, GitHub, Notion, Dropbox, Gmail, Linear, Salesforce, SharePoint, Teams, "
            "Zendesk, Asana, and PagerDuty. Each connector extracts resources, maps fine-grained "
            "source permissions into Zanzibar viewer, editor, and owner tuples, and supports "
            "cursor-based incremental sync managed by the Scribe background worker."
        ),
        "allowed_users": ["alice", "bob", "charlie", "anonymous"],
    },
    {
        "id": "doc-idp-06",
        "title": "Identity Federation, SCIM and Group Alias Expansion",
        "uri": "https://wiki.corp.internal/identity/group-expansion",
        "tenant_id": "corp-default",
        "content": (
            "Identity federation in AegisMind maps external IdP groups from Okta, Entra ID, and "
            "Google Workspace into canonical Zanzibar group identifiers. When evaluating access, "
            "AegisMind recursively expands nested group memberships (e.g. group:engineers#member "
            "to group:infrastructure#member) ensuring effective permissions accurately reflect "
            "corporate directory hierarchies."
        ),
        "allowed_users": ["alice", "bob"],
    },
    {
        "id": "doc-redteam-07",
        "title": "Permission Red Team Guardrails and Rule 5 Verification",
        "uri": "https://wiki.corp.internal/security/redteam-guardrails",
        "tenant_id": "corp-default",
        "content": (
            "The AegisMind Permission Red Team verification suite rigorously tests multi-tenant "
            "isolation, anti-bypass boundaries, and Rule 5 compliance. Static code analysis "
            "and runtime assertions enforce that no anti-bot bypass, cookie replay, or "
            "credential spoofing is permitted anywhere in connector or retrieval code."
        ),
        "allowed_users": ["alice"],
    },
    {
        "id": "doc-lens-08",
        "title": "Lens Web UI and Conversational Search Experience",
        "uri": "https://wiki.corp.internal/lens/user-guide",
        "tenant_id": "corp-default",
        "content": (
            "Lens is the reference web interface for AegisMind built with React 19, Vite, and "
            "Tailwind CSS. Lens features conversational search with Server-Sent Events (SSE) "
            "streaming, deep-linked citations, instant hybrid search, connector management, "
            "and an interactive Zanzibar relationship graph viewer showing effective permissions."
        ),
        "allowed_users": ["alice", "bob", "charlie", "anonymous"],
    },
]


async def seed_initial_knowledge(
    vector_store: MemoryVectorStoreAdapter,
    authz: MemoryAuthzAdapter,
    embedder: MockEmbedderAdapter,
) -> list[dict[str, Any]]:
    """Seed initial access-controlled knowledge corpus and Zanzibar relationship tuples."""
    chunks: list[Chunk] = []
    tuples: list[RelationshipTuple] = []
    indexed_resources: list[dict[str, Any]] = []

    for _idx, doc in enumerate(INITIAL_DOCUMENTS, start=1):
        content = doc["content"]
        embedding = await embedder.embed_query(content)
        sparse_embedding = await embedder.embed_sparse_query(content)

        chunk = Chunk(
            id=f"chunk-{doc['id']}-01",
            document_id=doc["id"],
            index=1,
            content=content,
            embedding=embedding,
            sparse_embedding=sparse_embedding,
            metadata={
                "title": doc["title"],
                "uri": doc["uri"],
                "tenant_id": doc["tenant_id"],
            },
            acl=ACL(
                is_public="anonymous" in doc["allowed_users"],
                allowed_principals=[f"user:{u}" for u in doc["allowed_users"]],
            ),
        )
        chunks.append(chunk)

        # Write Zanzibar viewer relationship tuples
        for user in doc["allowed_users"]:
            tuples.append(
                RelationshipTuple(
                    resource=f"document:{doc['id']}",
                    relation="viewer",
                    subject=f"user:{user}",
                )
            )

        indexed_resources.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "uri": doc["uri"],
                "tenant_id": doc["tenant_id"],
                "chunks_count": 1,
            }
        )

    await vector_store.upsert(chunks)
    await authz.write_tuples(tuples)
    logger.info("Seeded %d knowledge chunks and %d Zanzibar tuples", len(chunks), len(tuples))
    return indexed_resources


def discover_connectors() -> dict[str, Any]:
    """Discover available connectors via entry points or direct imports."""
    connectors: dict[str, Any] = {}
    try:
        discovered_names = list_adapters("connectors")
        for name in discovered_names:
            try:
                connector_cls = resolve_adapter("connectors", name)
                connectors[name] = connector_cls()
            except Exception as exc:
                logger.debug("Could not instantiate discovered connector '%s': %s", name, exc)
    except Exception as exc:
        logger.debug("Entry point connector discovery skipped: %s", exc)

    # Standard connector list fallback for known connectors
    standard_connectors = [
        ("confluence", "aegismind_connector_confluence", "ConfluenceConnector"),
        ("jira", "aegismind_connector_jira", "JiraConnector"),
        ("google_drive", "aegismind_connector_google_drive", "GoogleDriveConnector"),
        ("slack", "aegismind_connector_slack", "SlackConnector"),
        ("github", "aegismind_connector_github", "GitHubConnector"),
        ("notion", "aegismind_connector_notion", "NotionConnector"),
        ("dropbox", "aegismind_connector_dropbox", "DropboxConnector"),
        ("linear", "aegismind_connector_linear", "LinearConnector"),
    ]

    for name, module_name, class_name in standard_connectors:
        if name not in connectors:
            try:
                import importlib

                mod = importlib.import_module(module_name)
                cls = getattr(mod, class_name, None)
                if cls is not None:
                    connectors[name] = cls()
            except Exception as exc:
                logger.debug("Failed loading fallback connector '%s': %s", name, exc)

    return connectors


async def init_default_core_state() -> CoreState:
    """Initialize a fully operational CoreState with pre-seeded pipeline and knowledge."""
    from aegismind_retrieval.adapters_model import MockQueryRewriterAdapter

    vector_store = MemoryVectorStoreAdapter()
    authz = MemoryAuthzAdapter()
    embedder = MockEmbedderAdapter(dimension=64)
    reranker = MockRerankerAdapter()
    query_rewriter = MockQueryRewriterAdapter()

    pipeline = RetrievalPipeline(
        authz=authz,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
        query_rewriter=query_rewriter,
    )

    state = CoreState(
        retrieval_pipeline=pipeline,
        authz=authz,
        vector_store=vector_store,
    )

    indexed = await seed_initial_knowledge(vector_store, authz, embedder)
    state.indexed_resources = indexed
    state.connectors = discover_connectors()

    return state
