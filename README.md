# AegisMind: Enterprise Knowledge Engine with Zanzibar ACL & n8n Automation

Modular enterprise knowledge platform and offline sovereign AI agent with document-level Zanzibar access control enforced at retrieval.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Architecture](https://img.shields.io/badge/architecture-hexagonal%20%2F%20ports%20%26%20adapters-orange.svg)](#architecture)
[![Authz](https://img.shields.io/badge/authz-Zanzibar%20%2F%20SpiceDB-green.svg)](#permission-and-security-model)
[![Linter](https://img.shields.io/badge/linter-ruff-purple.svg)](https://github.com/astral-sh/ruff)
[![Tests](https://img.shields.io/badge/tests-194%20passing-brightgreen.svg)](#testing--quality)
[![Frontend](https://img.shields.io/badge/UI-React%2019%20%2F%20Vite-cyan.svg)](apps/lens)

---

---

AegisMind is an open-source, modular enterprise knowledge and retrieval platform engineered around clean hexagonal architecture (Ports and Adapters). It guarantees mathematical document-level authorization using Google Zanzibar-style Relation-Based Access Control (ReBAC) powered by SpiceDB.

In addition to enterprise-scale multi-tenant retrieval, AegisMind includes a **Local Sovereign Agent Mode**: a 100% offline, air-gapped personal intelligence layer that runs locally alongside the enterprise stack. It utilizes local Ollama models, zero-network ONNX embeddings, a lightweight SQLite vector store, and strictly sandboxed system tools.

---

## Key Features

- **Authz-Before-Rerank Pipeline**: Document permissions are evaluated *during* retrieval before cross-encoder reranking and token budgeting. Unauthorized chunks are purged upfront, preventing permission leakage, cache poisoning, and prompt injection attacks.
- **7-Stage Hybrid Retrieval**:
  1. Input validation and query preprocessing
  2. Dense vector search and BM25/lexical sparse search
  3. Reciprocal Rank Fusion (RRF)
  4. Candidate Overfetching (3x to 5x requested top_k)
  5. Bulk Zanzibar Authorization check with `at_least_as_fresh` consistency
  6. Cross-encoder relevance reranking
  7. Token budgeting and synthesis
- **Local Sovereign Agent Mode**: Completely air-gapped personal agentic workflow operating on local machines. Zero external API calls, zero cloud dependencies.
- **Sandboxed Agent Tools**:
  - `search_local_knowledge`: Queries local offline vector storage.
  - `read_system_file`: Access restricted strictly to allowlisted root directories; path traversal (`..`) is strictly blocked.
  - `create_note`: Persists structured Markdown notes with YAML frontmatter to `.aegismind/notes/`.
  - `run_local_command`: Strictly restricted to an allowlist of read-only diagnostic utilities (`git status`, `git log`, `docker ps`, `uptime`, etc.), rejects all shell metacharacters, executed via `shlex.split` argv lists with timeout and structured audit logs.
- **Sovereign Embeddings and Storage**: Pluggable support for zero-GPU ONNX embeddings via FastEmbed (`bge-small-en-v1.5`), local Ollama embeddings, and an in-process SQLite vector store supporting dense cosine, lexical, and hybrid search.
- **Extensible Connector SDK**: Ingest data from 15+ sources with strict conformance tests, change detection, and sensitive-path denylists.
- **Lens Web UI**: Clean React 19 interface with real-time Chat, Datasets exploration, a dedicated Notes Vault, and a live Local Tools transparency audit feed.

---

## Architecture

AegisMind strictly follows the Ports and Adapters (hexagonal) pattern. Domain logic, service boundaries, and pipeline abstractions define pure Python protocols (Ports). Concrete storage engines, embedders, authorization backends, and models (Adapters) register via Python entry points and are resolved dynamically at runtime through `aegismind_core.registry`.

```
                             +---------------------------------------+
                             |         Lens Web UI (React 19)        |
                             |  [Chat] [Notes Vault] [Tools Panel]   |
                             +-------------------+-------------------+
                                                 | HTTP / REST
                                                 v
+------------------------------------------------------------------------------------+
|                               Agora API Server (FastAPI)                           |
+----------------------------------------+-------------------------------------------+
| Enterprise RAG Pipeline                | Local Sovereign Agent                     |
| 1. Query Preprocessing                 | - SovereignAgentLoop (ReAct Engine)       |
| 2. Dense + Lexical Search              | - Local Ollama LLM (Qwen 2.5 / Llama 3.2) |
| 3. Reciprocal Rank Fusion (RRF)        | - Sandboxed System Tools:                 |
| 4. Overfetch (3x-5x top_k)             |   * search_local_knowledge                |
| 5. Bulk Zanzibar Authz (SpiceDB)       |   * read_system_file (Restricted Roots)   |
| 6. Cross-Encoder Reranking             |   * create_note (Markdown + Frontmatter)  |
| 7. Token Budgeting & Synthesis         |   * run_local_command (Allowlist Only)    |
+-------------------+--------------------+---------------------+---------------------+
                    |                                          |
                    v                                          v
+----------------------------------------+   +---------------------------------------+
| Enterprise Adapters (Scale)            |   | Sovereign Adapters (Air-Gapped)       |
| - Postgres + pgvector Storage          |   | - SQLite Vector Store (In-Memory/File)|
| - SpiceDB Zanzibar ReBAC               |   | - FastEmbed ONNX / Ollama Embedders   |
| - HuggingFace TEI Embedder & Reranker  |   | - Local Filesystem Connector          |
+----------------------------------------+   +---------------------------------------+
```

---

## Workspace Structure

The repository is organized as a monorepo managed with `uv` workspaces for Python and `pnpm` workspaces for TypeScript:

```
aegisMind/
├── packages/
│   ├── aegismind-core/          # FastAPI Agora server, orchestration, registry, sovereign agent
│   ├── aegismind-types/         # Domain models, chunk structures, authorization envelopes
│   ├── aegismind-authz/         # SpiceDB Zanzibar ReBAC adapter and in-memory authorization
│   ├── aegismind-retrieval/     # Vector stores (pgvector, SQLite), embedders, rerankers, RRF
│   ├── aegismind-ingestion/     # Text chunking, document parsers, versioning
│   ├── aegismind-identity/      # Identity propagation and group alias expansion
│   ├── aegismind-infra/         # Secrets manager and object storage adapters
│   ├── aegismind-connector-sdk/ # Connector interface, verify harness, manifest validator
│   └── aegismind-mcp-bridge/    # Model Context Protocol bridge
├── connectors/
│   ├── local_filesystem/        # Offline filesystem connector with security denylists
│   ├── confluence/              # Atlassian Confluence connector
│   ├── github/                  # GitHub repositories and pull requests connector
│   ├── google_drive/            # Google Drive connector
│   ├── jira/                    # Jira issue tracking connector
│   ├── notion/                  # Notion workspace connector
│   ├── slack/                   # Slack conversation connector
│   └── ...                      # Dropbox, Gmail, Granola, Linear, Salesforce, Teams, Zendesk
├── apps/
│   └── lens/                    # React 19 + Vite web interface
├── deploy/
│   ├── docker/                  # Production Dockerfiles
│   └── migrations/              # Database schema migrations
└── tests/                       # Unit, integration, security guardrail, and agent test suites
```

---

## Quickstart: Running AegisMind

You can run AegisMind in either **Local Sovereign Agent Mode** (zero cloud setup) or **Full Enterprise Stack** (with Docker Compose).

### Option 1: Local Sovereign Agent Mode (100% Offline)

This mode operates completely on your machine without external cloud dependencies.

#### 1. Start Ollama
Ensure Ollama is running and pull a tool-calling capable model:
```bash
ollama serve
ollama pull qwen2.5:7b
```
*(Alternative lightweight model: `ollama pull llama3.2:3b`)*

#### 2. Start the Agora Backend API
From the project root:
```powershell
uv run uvicorn aegismind_core.routes:app --reload --port 8000
```
- Swagger API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Agent Tools Listing: [http://localhost:8000/api/v1/agent/tools](http://localhost:8000/api/v1/agent/tools)
- Notes Vault API: [http://localhost:8000/api/v1/notes](http://localhost:8000/api/v1/notes)

#### 3. Start the Lens Web UI
In a separate terminal:
```powershell
pnpm --filter lens dev
```
Open [http://localhost:5173/](http://localhost:5173/) in your browser.
- **Chat**: Interact with the ReAct Sovereign Agent.
- **Notes**: Browse, search, and preview Markdown notes created by the agent.
- **Local Tools**: Inspect the live audit feed and allowed system commands.

---

### Option 2: Full Enterprise Stack (Docker Compose)

To spin up the complete enterprise infrastructure (PostgreSQL with pgvector, SpiceDB, HuggingFace TEI Embedder, TEI Reranker, and Agora API):

```powershell
docker compose up -d
```

Verify service health:
```powershell
docker compose ps
```

---

## Permission and Security Model

AegisMind treats authorization correctness as non-negotiable:

1. **Authz-Before-Rerank**:
   Standard RAG architectures rerank documents before filtering, which leaks document existence and wastes cross-encoder compute. AegisMind overfetches candidates (3x to 5x), checks all candidate chunk IDs in a single bulk call to SpiceDB, purges unauthorized items, and only passes authorized chunks to the reranker and synthesis stages.

2. **Zanzibar ReBAC Consistency**:
   All authorization checks execute with `at_least_as_fresh` consistency tokens, preventing stale permission evaluations after access revocation.

3. **Sovereign Agent Sandboxing**:
   - Path Traversal Guard: Any path containing `..` or targeting outside configured allowlist root directories is rejected before filesystem operations.
   - Command Execution Guard: Shell metacharacters (`;`, `|`, `&`, backticks, redirects) are rejected. Commands are tokenized via `shlex.split`, matched against an allowlist of read-only diagnostics, executed with strict timeouts, and recorded in structured audit logs.
   - Ingestion Denylist: Files matching `.ssh/`, `.env`, `*credentials*`, `*id_rsa*`, `.aws/`, `*.pem`, or `*.key` are skipped during indexing.

---

## Testing & Quality

AegisMind maintains strict quality standards across all packages.

### Run Unit and Agent Tests
```powershell
uv run pytest -v
```

### Run Static Type Checking
```powershell
uv run mypy packages connectors tests
```

### Run Code Formatting and Linting
```powershell
uv run ruff check .
uv run ruff format --check .
```

### Build Frontend
```powershell
pnpm --filter lens build
```

---

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
