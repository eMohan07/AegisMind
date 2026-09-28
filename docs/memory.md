# AegisMind Long-Term Memory System

## 1. Overview and Architecture

AegisMind implements a local-only, sovereign long-term memory system designed for single-user privacy and transparent governance.
All storage, indexing, retrieval, and extraction run strictly on localhost. No cloud APIs, no telemetry, and no outbound network calls are made.

The memory architecture follows the ports and adapters pattern:
- **Port Protocol**: `MemoryStorePort` in `aegismind_core.memory.port` defines the interface contract for memory persistence, querying, namespace isolation, audit tracking, and backup/restore.
- **SQLite Adapter**: `SQLiteMemoryStore` in `aegismind_core.memory.sqlite_store` provides the unified SQLite engine using WAL mode, FTS5 lexical indexing, and vector similarity search.
- **Extraction Pipeline**: `MemoryExtractor` in `aegismind_core.memory.extractor` queries local Ollama models (`/api/generate`) with automatic deduplication, contradiction handling, and strict private mode guards.
- **Retrieval and Injection**: Context injection formats memories into XML tags (`<memory><fact ...>...</fact></memory>`) and reports `memories_used` back to the user.
- **Consolidation**: `MemoryConsolidator` in `aegismind_core.memory.consolidation` runs periodic maintenance to purge tombstones, archive stale episodic memories, and merge similar semantic records.

---

## 2. Database Schema

The SQLite store (`ltm.db`) manages three primary tables alongside automated triggers and full-text virtual tables:

### 2.1 `memories` Table
```sql
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    entities_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 1.0,
    importance REAL NOT NULL DEFAULT 0.5,
    status TEXT NOT NULL DEFAULT 'pending',
    pinned INTEGER NOT NULL DEFAULT 0,
    sensitivity TEXT NOT NULL DEFAULT 'normal',
    source_thread_id TEXT,
    source_message_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    valid_from TEXT,
    valid_to TEXT,
    superseded_by TEXT,
    content_hash TEXT NOT NULL,
    embedding BLOB
);
```

### 2.2 `memories_fts` Virtual Table
FTS5 full-text search table with automatic synchronization via triggers:
- `AFTER INSERT`: Inserts row into `memories_fts`.
- `AFTER UPDATE`: Synchronizes modified content.
- `AFTER DELETE`: Deletes row from `memories_fts`.

### 2.3 `memory_events` Append-Only Audit Table
Cryptographic hash-chaining log for non-repudiation:
```sql
CREATE TABLE memory_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
```
**Tamper Protection**: SQLite triggers `trg_memory_events_no_update` and `trg_memory_events_no_delete` raise `ABORT` on any attempt to update or delete audit records.

---

## 3. Memory Types and Lifecycle

### 3.1 Memory Types
1. **Semantic**: Core facts, domain knowledge, and enduring statements.
2. **Episodic**: Event descriptions tied to a specific timestamp or conversation.
3. **Procedural**: Instructions, operational steps, or workflow rules.
4. **Preference**: User preferences regarding formatting, themes, language, or tone.

### 3.2 Status Lifecycle
- **`pending`**: Newly extracted candidate memories await explicit user approval.
- **`active`**: Approved memories actively retrieved and injected into chat context.
- **`rejected`**: Discarded by user during pending review.
- **`superseded`**: Replaced by newer or updated contradictory facts; historical chain preserved.
- **`forgotten`**: Tombstoned by user request; excluded from retrieval until physical purge.

---

## 4. Hybrid Retrieval and Scoring Formula

AegisMind uses a hybrid retrieval model combining lexical FTS5 BM25 search, dense vector cosine similarity, Reciprocal Rank Fusion (RRF), importance weighting, temporal exponential decay, and pin boost:

$$\text{RRF}(m) = \sum_{l \in \{\text{FTS5}, \text{Vector}\}} \frac{1}{60 + \text{rank}_l(m)}$$

$$\text{Composite Score} = 0.55 \cdot \frac{\text{RRF}(m)}{\text{max\_RRF}} + 0.25 \cdot \text{importance} + 0.20 \cdot 2^{-\frac{\Delta t}{30}} + (0.05 \text{ if pinned else } 0)$$

Where:
- $\Delta t$: Days elapsed since creation or last update.
- Half-life: 30 days for temporal recency decay.
- Pinned boost: Constant $+0.05$ bonus ensuring critical memories remain prominent.

---

## 5. Security and Privacy Guarantees

1. **Zero-Leakage Local Boundary**: All memory operations execute strictly against SQLite on local disk and Ollama on localhost. No outbound network requests are initiated.
2. **Pre-Write Secret Guard**: Content is scanned across 7 regex patterns before saving:
   - API keys and tokens
   - Private key PEM headers and bodies
   - Password assignments
   - Bearer tokens
   - AWS access keys
   - GitHub personal access tokens
3. **Private Mode Isolation**: When `private_mode=True` is supplied to chat endpoints:
   - Long-term memory retrieval is skipped completely.
   - Post-conversation memory extraction is disabled.
4. **Append-Only Tamper-Evident Audit**: Every mutation (creation, update, approval, rejection, forget, supersede) appends an immutable block linked by SHA-256 hash chains.
5. **WAL-Safe Backups**: Online backups utilize the native SQLite backup API, ensuring active WAL pages are flushed and captured without locking out readers.
