# Architectural Audit: Permission Cache Invalidation and Zero-Stale Guarantee

## Executive Statement
AegisMind guarantees that no authorization decision or search result is cached across intermediate application layers (Agora API, Lens web portal, scout browser extension, or backend services). Every retrieval query executes a real-time, live authorization evaluation against Zanzibar (SpiceDB) using `at_least_as_fresh` consistency.

## Layer-by-Layer Verification

### 1. Agora REST API Layer (`packages/aegismind-core/src/aegismind_core/routes.py`)
- **Status**: Verified Zero-Cache.
- **Audit Details**: Neither `/api/v1/search` nor `/api/v1/chat` utilizes HTTP caching headers (`Cache-Control: no-store` enforced), in-memory response caches, or Redis caches for query results. Every request instantiates a new execution through `RetrievalPipeline.execute`.

### 2. Retrieval Pipeline (`packages/aegismind-retrieval/src/aegismind_retrieval/pipeline.py`)
- **Status**: Verified Live Round-Trip.
- **Audit Details**:
  - Stage 5 explicitly invokes `authz.bulk_check` for every candidate chunk set.
  - Consistency level is strictly enforced as `at_least_as_fresh` using the caller's consistency token (or latest revision).
  - No permission lookup table or cache is persisted in the pipeline instance between search executions.

### 3. SpiceDB ReBAC Engine (`packages/aegismind-authz/src/aegismind_authz/adapters/spicedb.py`)
- **Status**: Zero-Stale Read Window.
- **Audit Details**:
  - SpiceDB evaluates permissions against its relational datastore using consistent revision snapshots.
  - When a relationship tuple is deleted via `authz.delete_relationship`, the deletion is committed synchronously and returns a zed token.
  - Immediate subsequent checks with `at_least_as_fresh` guarantee that the revoked permission cannot be used.

### 4. Optional Event-Driven Invalidation via SpiceDB Watch API
- To support any enterprise deployment adding distributed read replicas or edge caching, AegisMind includes `SpiceDBWatcher` in `aegismind_authz.watch`.
- The watcher streams `TOUCH` and `DELETE` updates from SpiceDB's gRPC Watch API and triggers invalidation callbacks within milliseconds of tuple deletion.
