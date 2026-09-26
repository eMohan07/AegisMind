# AegisMind: Enterprise Knowledge Engine with Zanzibar ACL & n8n Automation

**AegisMind** is a production-grade, multi-tenant enterprise knowledge retrieval and RAG engine built on clean architectural principles (Ports and Adapters). It integrates dynamic fine-grained access control (**SpiceDB Zanzibar**), hybrid vector search (**pgvector** / **BAAI BGE-M3**), reciprocal rank fusion (RRF), overfetching, and an **n8n Workflow Automation Layer**.

---

## 🌟 Key Features

- **🔐 Strict Zero-Trust Authorization**: SpiceDB Google Zanzibar implementation enforcing document-level ACLs. Unauthorized candidates are pruned *before* re-ranking to guarantee zero stale reads or privacy leaks.
- **⚡ Hybrid Vector Search & Reranking**: Dense & sparse vector search via `pgvector` paired with BGE-M3 dense embeddings and BGE-Reranker-v2 for state-of-the-art retrieval accuracy.
- **🤖 Integrated n8n Automation Engine**: Pre-built orchestration workflows for automated document sync, Slack RAG bot, DLQ monitoring, daily LLM digests, and HR ACL provisioning.
- **🖥️ Lens Web Interface**: Modern, reactive web application (React, Vite, Tailwind CSS, Lucide Icons) featuring Chat RAG, Search, Connector management, Access Graph visualizer, and an interactive **Automation (n8n)** dashboard.
- **🪶 Lightweight & Resource-Optimized**: Fully containerized stack optimized for minimal memory and disk footprint (~450 MB image downloads vs 6+ GB traditional stacks).

---

## 🏗️ Architecture Overview

```
                      +-----------------------------+
                      |       Lens Web UI           |
                      |  (React + Vite - Port 5173) |
                      +--------------+--------------+
                                     |
                                     v
+------------------+       +---------+----------+       +-------------------+
|  n8n Automation  | ----> |   Agora Core API   | <---- | External Webhooks |
|    (Port 5678)   |       |  (FastAPI - 8000)  |       | (Slack, Okta, GDrive)
+------------------+       +---------+----------+       +-------------------+
                                     |
             +-----------------------+-----------------------+
             |                                               |
             v                                               v
+------------+------------+                     +------------+------------+
|  SpiceDB Zanzibar ACL   |                     | PostgreSQL (pgvector)     |
|   (gRPC - Port 50051)   |                     |   (SQL & Vector Storage)  |
+-------------------------+                     +-------------------------+
```

---

## 🚀 Quick Start

### Option 1: Docker Compose (Recommended)

1. Ensure **Docker Desktop** is open and running.
2. Start the lightweight containerized stack:

```powershell
# Navigate to repository root
cd AegisMind

# Start all services
docker compose up -d
```

3. Access services:
   - **Lens Web UI**: [http://localhost:5173](http://localhost:5173)
   - **n8n Automation Dashboard**: [http://localhost:5678](http://localhost:5678) *(Login: `admin` / `change_me_n8n_password`)*
   - **Agora Core REST API**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **SpiceDB gRPC Service**: `localhost:50051`

*(Note: OCR PDF processing via `docling` is optional and can be enabled via `docker compose --profile ocr up -d`)*

---

### Option 2: Local Development Mode (Python + Vite)

If running without Docker:

```powershell
# 1. Install Python dependencies using uv
uv sync --all-groups
uv pip install -e packages/aegismind-types -e packages/aegismind-authz -e packages/aegismind-retrieval -e packages/aegismind-core -e packages/aegismind-connector-sdk -e packages/aegismind-identity -e packages/aegismind-infra -e packages/aegismind-ingestion -e packages/aegismind-mcp-bridge -e .

# 2. Install Frontend dependencies
pnpm install

# 3. Start Backend API (FastAPI)
uv run uvicorn aegismind_core.app:create_app --factory --reload --port 8000

# 4. Start Lens Frontend (In a separate terminal)
pnpm --filter lens dev
```

---

## 🔄 Pre-Built n8n Workflows

All workflows are located in `./n8n/workflows/` and auto-load on startup:

| ID | Workflow Name | Trigger | Functionality |
|---|---|---|---|
| **01** | `Document Ingestion` | Webhook (`/webhook/aegismind/ingest`) | Ingests documents from external webhooks into AegisMind |
| **02** | `Connector Scheduled Sync` | Schedule (Cron) | Polls connectors every 6h and triggers automatic index syncs |
| **03** | `Slack Search Bot` | Slack Event Webhook | Responds in Slack threads with Zanzibar-permissioned search answers |
| **04** | `DLQ Monitor & Retry` | Schedule (30m) | Monitors failed ingestions, retries up to 3x, alerts on persistent errors |
| **05** | `Daily Audit Digest` | Schedule (Daily 8 AM) | Generates executive LLM summary of daily system activity & ingestions |
| **06** | `ACL Provisioning` | HR Webhook | Automatically grants or revokes SpiceDB tuples on employee onboard/offboard |

---

## 🧪 Testing & Verification

To run unit tests across packages:

```powershell
uv run pytest
```

To build and verify the Lens frontend bundle:

```powershell
cd apps/lens
npm run build
```

---

## 📂 Repository Structure

```
AegisMind/
├── apps/
│   └── lens/                   # React + Vite frontend application
├── n8n/
│   ├── workflows/              # Pre-configured n8n workflow JSONs
│   └── README.md               # Detailed n8n setup guide
├── packages/
│   ├── aegismind-authz/        # SpiceDB Zanzibar authorization adapter
│   ├── aegismind-core/         # Domain models, routes, and retrieval pipeline
│   ├── aegismind-retrieval/    # Vector search, MMR, overfetching & reranking
│   └── aegismind-types/        # Core type definitions
├── deploy/                     # Dockerfiles & Database init scripts
├── compose.yaml                # Docker Compose orchestration
└── README.md                   # Project documentation
```

---

## 🛡️ Security Guarantees

1. **Pre-Rerank ACL Enforcement**: Candidate documents are checked against SpiceDB Zanzibar *before* re-ranking, eliminating data leaks or unauthorized snippet scoring.
2. **Overfetching Factor**: Configurable overfetching factor (default 4x top_k) ensures high recall even after strict ACL filtering.
3. **Multi-Tenancy**: Isolated tenant boundaries with tenant-scoped Zanzibar namespaces.
