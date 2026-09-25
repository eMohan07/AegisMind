# AegisMind Consistency Model Specification

## 1. Executive Summary

AegisMind implements a tiered consistency architecture designed to balance three critical enterprise operational guarantees:
1. Strict authorization safety: zero unauthorized data leaks across permission transitions.
2. High-throughput ingestion: minimizing expensive re-embedding compute via cryptographic chunk hashing.
3. Sub-second interactive search: preserving fast vector and hybrid retrieval under concurrent document and ACL mutations.

To achieve these guarantees simultaneously without distributed lock contention, AegisMind segments consistency domains into three distinct models:
- Read-Your-Writes consistency for document update transactions within the ingestion boundary.
- Causal Consistency with zedtoken ordering for Zanzibar (SpiceDB) permission changes.
- Eventual Consistency with atomic tombstoning for vector and lexical index synchronization.

---

## 2. Consistency Guarantees by Subsystem

### 2.1 Causal Consistency for Permission Changes (SpiceDB / Zanzibar)

The most critical security invariant of AegisMind is that permissions MUST be causally consistent. An unauthorized user must never observe search results from candidate chunks that their current identity is forbidden from accessing.

```
+------------------+         (1) Write Tuples          +----------------------+
| Ingestion Worker | --------------------------------> |   SpiceDB Cluster    |
+------------------+                                   +----------------------+
         |                                                        |
         | (2) Get ZedToken                                       | (3) Return ZedToken
         v                                                        v
+------------------+        (4) Enforce Token          +----------------------+
| Vector Indexing  | --------------------------------> | Sacred Pipeline Read |
+------------------+     (at_least_as_fresh=ZedToken)  +----------------------+
```

Key characteristics:
1. **Pre-Indexing Permission Commitment**: Before newly ingested or updated document chunks are written to the vector store or made searchable, relationship tuples are committed to SpiceDB via `authz.write_tuples()`.
2. **Revision Token Freshness**: SpiceDB returns a monotonically advancing `ZedToken` representing the snapshot of the permission transaction.
3. **Pipeline Evaluation at Least as Fresh**: During Stage 5 of the retrieval pipeline, the bulk Zanzibar evaluation executes with `TokenConsistency(requirement="at_least_as_fresh", token=target_token)`. This eliminates read-after-write anomalies: queries initiated after a permission change observe that change immediately or wait for read replica convergence.
4. **Instant Revocation Invalidation**: When permissions are revoked or deleted, the `SpiceDBWatcher` gRPC stream receives the tombstone event in sub-millisecond latency, invalidating local decision caches and enforcing zero-stale access windows.

### 2.2 Read-Your-Writes Consistency for Ingestion Pipelines

For connectors and operators managing document lifecycles, AegisMind guarantees Read-Your-Writes within the ingestion worker context:

```
Version N Ingestion Flow:
[Parse Document] 
       |
       v
[Update SpiceDB Tuples] (Causal barrier: permissions active first)
       |
       v
[Compute SHA-256 Hashes per Chunk]
       |
       +---> Matching Hash? ---> Reuse cached vector embedding (Zero GPU / Model cost)
       |
       +---> New Hash?     ---> Embed chunk via BGE-M3 (dense + sparse)
       |
       v
[Atomic Soft-Delete Version N-1 Chunks] (is_deleted = TRUE, deleted_at = NOW())
       |
       v
[Upsert Version N Chunks] (version = N, is_deleted = FALSE)
```

Key characteristics:
1. **Atomic Soft-Delete and Replacement**: When a document with an existing `document_id` is re-ingested with modified text, its prior chunks are marked as tombstones (`is_deleted=TRUE, deleted_at=timestamp`). New chunks are written with `version = N + 1`.
2. **Deterministic Content Hashing**: Every chunk computes a SHA-256 digest of its canonical payload (`contextual_prefix + content`). If an identical chunk content hash exists from a prior version, the existing dense (1024-dim) and sparse token embeddings are preserved directly, avoiding redundant external embedding API calls.
3. **Tombstone Exclusion**: All active search operations (`query_dense`, `query_lexical`, and hybrid RRF) strictly filter out chunks with `is_deleted = TRUE`. A document update immediately reflects only the latest version in search results.

### 2.3 Eventual Consistency for Vector Index Synchronization

While permission boundaries and document versions are strictly ordered, vector index maintenance operates under bounded eventual consistency:

```
[Write Active Chunks] ---> [Postgres / pgvector table] (Immediately visible via sequential scan)
                                    |
                                    v (Background / Asynchronous)
                           [HNSW / StreamingDiskANN Graph Updates]
                                    |
                                    v
                           [Periodic Vacuum Worker] (Hard-delete tombstones > 24h)
```

Key characteristics:
1. **Index Graph Convergence**: In pgvectorscale and Qdrant, newly inserted chunks are immediately written to durable tables and are searchable via coarse pre-filtering and exact distance calculation. HNSW and StreamingDiskANN graph indexes incorporate new vectors asynchronously to maintain maximum query throughput.
2. **Vacuum and Tombstone Cleanup**: Soft-deleted chunks remain in storage to support audit inspection, time-travel debugging, and ongoing inflight transactions. A periodic background vacuum process permanently deletes tombstoned chunks older than a configurable retention horizon (default: 86,400 seconds / 24 hours).

---

## 3. Ingestion Lifecycle State Machine

The following table details state transitions for document chunks across updates:

| State | `is_deleted` | `deleted_at` | Searchable? | Re-embedding required? |
|---|---|---|---|---|
| **New Chunk** | `FALSE` | `NULL` | Yes (after SpiceDB sync) | Yes (computed on ingest) |
| **Unchanged Chunk (v2)** | `FALSE` | `NULL` | Yes | No (reused via SHA-256 match) |
| **Modified Chunk (v2)** | `FALSE` | `NULL` | Yes | Yes (new hash generated) |
| **Superseded Chunk (v1)**| `TRUE` | `TIMESTAMPTZ` | No (filtered at query time) | N/A |
| **Vacuumed Chunk** | Record deleted | N/A | No (purged from storage) | N/A |

---

## 4. Verification and Audit

The consistency model is validated through automated test suites:
- `tests/integration/test_permission_revocation_zero_stale.py`: Verifies zero stale reads following tuple deletion.
- `tests/security/test_tenant_isolation.py`: Verifies multi-tenant isolation barriers.
- `tests/test_document_versioning.py`: Verifies SHA-256 hash matching, vector reuse, atomic tombstoning, and vacuuming.
