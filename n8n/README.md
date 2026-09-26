# AegisMind + n8n Automation

n8n is an open-source workflow automation platform. This integration gives AegisMind a
full orchestration layer — scheduled syncs, Slack bots, ACL provisioning, DLQ monitoring,
and daily digests — all wired to the Agora REST API without writing any additional code.

## Stack

| Component | Port | Purpose |
|-----------|------|---------|
| n8n | 5678 | Workflow automation engine |
| AegisMind Agora | 8000 | Core API (n8n calls this) |
| Slack | external | Notifications & search bot |

## Quick Start

```bash
# 1. Start the full stack including n8n
docker compose up -d

# 2. Open n8n
open http://localhost:5678
# Login: admin / aegismind_n8n_password (or value from .env)

# 3. Workflows are auto-imported from ./n8n/workflows/
#    Activate each workflow in the n8n UI
```

## Workflows

### 1. Document Ingestion Pipeline (`01_document_ingestion.json`)
**Trigger:** `POST http://localhost:5678/webhook/aegismind/ingest`

Accepts documents from any upstream source and pushes them through
the AegisMind ingestion API with full error handling.

```bash
# Ingest a document
curl -X POST http://localhost:5678/webhook/aegismind/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Q4 2026 Financial Report",
    "content": "Quarterly earnings exceeded projections by 12%...",
    "tenant_id": "corp-finance",
    "allowed_users": ["alice", "bob", "charlie"]
  }'

# GitHub webhook — point your repo webhook here, it auto-normalizes commits
# Slack file_shared event — forward from Slack Events API
```

**Flow:** Webhook -> Normalize Payload -> `POST /api/v1/documents` -> Slack notification

---

### 2. Connector Scheduled Sync (`02_connector_scheduled_sync.json`)
**Trigger:** Every 6 hours (cron)

Discovers all registered connectors via `GET /api/v1/connectors` and triggers
`sync` for each one sequentially. Sends a Slack summary with chunk counts per connector.

**Change sync interval:** Edit the "Every 6 Hours" Schedule Trigger node in n8n UI.

---

### 3. Slack Search Bot (`03_slack_search_bot.json`)
**Trigger:** `POST http://localhost:5678/webhook/aegismind/slack/events`

Point your Slack App's **Event Subscriptions URL** here. The bot responds in-thread
with top-3 results whenever it is @mentioned or DMed.

**Setup:**
1. Create a Slack App at https://api.slack.com/apps
2. Enable Event Subscriptions — URL: `http://<your-host>:5678/webhook/aegismind/slack/events`
3. Subscribe to `app_mention` and `message.im` events
4. Add `chat:write`, `channels:history`, `im:history` OAuth scopes
5. Add Slack credentials in n8n (Settings -> Credentials -> Slack API)

**Usage in Slack:**
```
@AegisMind what is our remote work policy?
```

---

### 4. DLQ Monitor & Auto-Retry (`04_dlq_monitor_retry.json`)
**Trigger:** Every 30 minutes + health check

- Fetches all `pending` DLQ items from `/api/v1/dlq`
- Items with `retry_count < 3` are automatically retried via `POST /api/v1/dlq/{id}/retry`
- Items with `retry_count >= 3` generate a Slack alert and are flagged as abandoned
- Simultaneously runs a health check against `/api/v1/health` and alerts on degraded status

---

### 5. Daily Audit Digest (`05_daily_audit_digest.json`)
**Trigger:** Weekdays at 8:00 AM

Posts a morning briefing to `#aegismind-digest` including:
- 24h activity breakdown (searches, ingestions, connector syncs)
- Top 5 most active users
- Full system readiness check (vector store, authz, embedder, reranker, LLM)

---

### 6. ACL Provisioning from HR System (`06_acl_provisioning.json`)
**Trigger:** `POST http://localhost:5678/webhook/aegismind/acl/provision`

Listens for HR system webhooks and automatically provisions Zanzibar
relationship tuples based on employee department/role:

```json
// Employee onboarded
{
  "event_type": "employee.onboarded",
  "employee_id": "carol",
  "department": "engineering",
  "role": "engineer",
  "tenant_id": "corp-default"
}

// Employee offboarded — auto-revokes all permissions
{
  "event_type": "employee.offboarded",
  "employee_id": "dave"
}
```

Supported departments: `engineering`, `finance`
Supported roles: `manager` (gets additional management-docs access)

---

## Environment Variables

Configure these in `.env` before starting:

| Variable | Default | Purpose |
|----------|---------|---------|
| `N8N_PORT` | `5678` | n8n UI and webhook port |
| `N8N_BASIC_AUTH_USER` | `admin` | n8n login username |
| `N8N_BASIC_AUTH_PASSWORD` | `change_me_n8n_password` | **Change this!** |
| `N8N_ENCRYPTION_KEY` | `change_me...` | Encrypts stored credentials **Change this!** |
| `AEGISMIND_API_KEY` | `` | API key for Agora (leave empty if not using auth) |
| `SLACK_CHANNEL_ALERTS` | `#aegismind-alerts` | Ops alerts channel |
| `SLACK_CHANNEL_DIGEST` | `#aegismind-digest` | Daily digest channel |

## Adding Custom Workflows

1. Create your workflow JSON in `./n8n/workflows/`
2. Restart n8n: `docker compose restart n8n`
3. Workflows appear in the n8n UI automatically

## Architecture

```
External Systems
  Slack Events API ──────┐
  GitHub Webhooks ───────┤
  HR System Webhooks ────┤
                         ▼
                   ┌─────────────┐
                   │    n8n      │  :5678
                   │  (Agora)    │
                   └──────┬──────┘
                          │  REST calls
                          ▼
                   ┌─────────────┐
                   │   Agora     │  :8000
                   │  FastAPI    │
                   └──────┬──────┘
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    PostgreSQL +      SpiceDB          TEI Embedder
    pgvector          (Zanzibar)       + Reranker
```

## Security Notes

- n8n stores Slack OAuth tokens and API keys encrypted using `N8N_ENCRYPTION_KEY`
- Change all default passwords before deploying to any non-local environment
- The `AEGISMIND_BASE_URL` inside n8n is `http://agora:8000` (internal Docker network) —
  this means n8n never exposes API calls to the public internet
- Webhook endpoints are publicly reachable; add n8n basic auth or reverse proxy
  authentication in front of `localhost:5678` in production
