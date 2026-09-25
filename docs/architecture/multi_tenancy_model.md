# Multi-Tenancy Architecture and Defense-in-Depth Specification

## Architectural Decision
AegisMind employs a **shared-infrastructure, strictly-isolated multi-tenant model**. Rather than deploying isolated compute and storage stacks per customer (which introduces high operational overhead and slow scaling), all tenants share core microservices (Agora API, Scribe worker, pgvectorscale, and SpiceDB) while enforcing strict tenant boundaries across every layer.

## Defense-in-Depth Isolation Layers

```
Layer 1: Identity & API Boundary
  └── Principal carries verified tenant_id from OIDC / JWT claim.

Layer 2: Storage & Index Scoping
  └── All tables (aegismind_records, aegismind_chunks, aegismind_envelopes, aegismind_feedback)
      include tenant_id column. Vector search enforces mandatory tenant_id pre-filtering.

Layer 3: PostgreSQL Row Level Security (RLS)
  └── Database policies restrict visibility using app.current_tenant session variable.

Layer 4: Zanzibar Authorization Boundary (SpiceDB)
  └── Object identifiers incorporate tenant boundaries (e.g. document:tenant_a#doc_1).
      Even if a ReBAC tuple was misconfigured to cross tenant borders,
      Layer 2 drops the candidates before they can ever be retrieved.
```

## Failure Mode Analysis: Misconfigured Zanzibar Tuples
If an administrative error or bug in an upstream connector causes a Zanzibar relation tuple to be written across tenants (for example: `document:tenant_victim#secret` granting `viewer` to `user:mallory` who belongs to `tenant_mallory`):
1. Mallory executes a query targeting `tenant_mallory`.
2. The retrieval pipeline constructs a mandatory pre-filter: `{"tenant_id": "tenant_mallory"}`.
3. The vector database (HNSW / DiskANN / In-Memory) evaluates the pre-filter and discards all chunks belonging to `tenant_victim`.
4. The candidate pool contains zero chunks from `tenant_victim`.
5. Mallory receives zero results. The misconfigured Zanzibar tuple is never exploited.
