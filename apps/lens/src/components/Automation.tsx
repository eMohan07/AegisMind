import * as React from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import {
  Workflow,
  Zap,
  Clock,
  MessageSquare,
  AlertTriangle,
  BarChart3,
  KeyRound,
  ExternalLink,
  Play,
  CheckCircle2,
  RefreshCw,
  X,
  ChevronDown,
  ChevronUp,
  Inbox,
  GitBranch,
  Slack,
  Brain,
  Settings2,
  ArrowRight,
} from "lucide-react";

const N8N_BASE = import.meta.env.VITE_N8N_URL || "http://localhost:5678";

// ─── Type definitions ──────────────────────────────────────────────────────────

interface WorkflowDef {
  id: string;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  trigger: "webhook" | "schedule" | "manual";
  triggerLabel: string;
  webhookPath?: string;
  schedule?: string;
  description: string;
  steps: string[];
  color: string;
  tag: string;
}

type RunStatus = "idle" | "running" | "success" | "error";

interface RunState {
  status: RunStatus;
  message?: string;
}

// ─── Workflow catalog ──────────────────────────────────────────────────────────

const WORKFLOWS: WorkflowDef[] = [
  {
    id: "01",
    icon: <Inbox className="h-5 w-5" />,
    title: "Document Ingestion Pipeline",
    subtitle: "Ingest docs from any source",
    trigger: "webhook",
    triggerLabel: "POST /webhook/aegismind/ingest",
    webhookPath: "/webhook/aegismind/ingest",
    description:
      "Accepts a POST request from GitHub webhooks, Slack file shares, or your own systems. Normalises the payload, pushes it through the AegisMind ingestion API, and sends a Slack success or failure alert automatically.",
    steps: [
      "Receive webhook from any source",
      "Normalise payload (GitHub, Slack, direct POST)",
      "Call POST /api/v1/documents",
      "Slack alert: ✅ success or ❌ failure",
    ],
    color: "from-emerald-500/20 to-emerald-500/5",
    tag: "ingestion",
  },
  {
    id: "02",
    icon: <RefreshCw className="h-5 w-5" />,
    title: "Connector Scheduled Sync",
    subtitle: "Auto-sync all connectors every 6h",
    trigger: "schedule",
    triggerLabel: "Every 6 hours",
    schedule: "0 */6 * * *",
    description:
      "Discovers all registered connectors (Notion, GitHub, Confluence, Slack, etc.) via the API, triggers a sync for each one in sequence, and posts a chunk-count summary to Slack when done.",
    steps: [
      "Wake up every 6 hours",
      "GET /api/v1/connectors → discover all",
      "POST /api/v1/connectors { action: 'sync' } for each",
      "Slack summary: connector name + chunks indexed",
    ],
    color: "from-blue-500/20 to-blue-500/5",
    tag: "sync",
  },
  {
    id: "03",
    icon: <Slack className="h-5 w-5" />,
    title: "Slack Search Bot",
    subtitle: "@mention → instant answers in Slack",
    trigger: "webhook",
    triggerLabel: "Slack Events API",
    webhookPath: "/webhook/aegismind/slack/events",
    description:
      "Wire this webhook to your Slack App's Event Subscriptions. When anyone @mentions the bot, it calls /api/v1/search with that user's Slack ID (so Zanzibar ACLs apply!), and replies in the same thread with the top-3 results and citations.",
    steps: [
      "Slack sends app_mention event",
      "Parse message, strip @mention",
      "POST /api/v1/search (with Slack user ID for ACL)",
      "Reply in-thread with results + citation links",
    ],
    color: "from-violet-500/20 to-violet-500/5",
    tag: "slack",
  },
  {
    id: "04",
    icon: <AlertTriangle className="h-5 w-5" />,
    title: "DLQ Monitor & Auto-Retry",
    subtitle: "Watch the dead-letter queue every 30m",
    trigger: "schedule",
    triggerLabel: "Every 30 minutes",
    schedule: "*/30 * * * *",
    description:
      "Every 30 minutes it fetches all pending DLQ items. Items with fewer than 3 retries are automatically retried. Items that have exceeded 3 retries get a Slack alert flagging them as abandoned. Simultaneously runs a health check and alerts if any subsystem is degraded.",
    steps: [
      "GET /api/v1/dlq?status=pending",
      "retry_count < 3 → POST /api/v1/dlq/{id}/retry",
      "retry_count ≥ 3 → Slack abandoned alert",
      "GET /api/v1/health → alert if unhealthy",
    ],
    color: "from-amber-500/20 to-amber-500/5",
    tag: "monitoring",
  },
  {
    id: "05",
    icon: <BarChart3 className="h-5 w-5" />,
    title: "Daily Audit Digest",
    subtitle: "Morning briefing every weekday at 8AM",
    trigger: "schedule",
    triggerLabel: "Weekdays 8:00 AM",
    schedule: "0 8 * * 1-5",
    description:
      "Posts a morning briefing to your Slack digest channel: 24-hour activity breakdown (searches, ingestions, connector syncs), top 5 most active users by principal ID, and a full system readiness report (vector store, SpiceDB, embedder, reranker, LLM).",
    steps: [
      "GET /api/v1/audit → compute 24h stats",
      "GET /api/v1/readiness → system health",
      "Format Slack message with stats + health",
      "Post to #aegismind-digest channel",
    ],
    color: "from-cyan-500/20 to-cyan-500/5",
    tag: "digest",
  },
  {
    id: "06",
    icon: <KeyRound className="h-5 w-5" />,
    title: "ACL Provisioning from HR",
    subtitle: "Auto-grant Zanzibar permissions on hire/fire",
    trigger: "webhook",
    triggerLabel: "POST /webhook/aegismind/acl/provision",
    webhookPath: "/webhook/aegismind/acl/provision",
    description:
      "Connect your HR system (BambooHR, Workday, Rippling, etc.) to this webhook. On employee.onboarded it maps their department and role to the correct Zanzibar relationship tuples and grants them instantly. On employee.offboarded it revokes all permissions in one shot.",
    steps: [
      "HR fires employee.onboarded / employee.offboarded",
      "Map dept + role → folder access rules",
      "POST /api/v1/relationships (grant) for each folder",
      "DELETE /api/v1/relationships on offboarding",
    ],
    color: "from-rose-500/20 to-rose-500/5",
    tag: "acl",
  },
];

// ─── Concept explainer cards ───────────────────────────────────────────────────

const CONCEPTS = [
  {
    icon: <Workflow className="h-5 w-5 text-primary" />,
    title: "What is n8n?",
    body: "n8n is an open-source workflow automation platform — think Zapier but self-hosted, code-friendly, and with no per-task pricing. You build visual workflows that connect APIs, databases, and services together without writing boilerplate glue code.",
  },
  {
    icon: <Brain className="h-5 w-5 text-violet-400" />,
    title: "Why does AegisMind use it?",
    body: "AegisMind exposes a powerful REST API but has no built-in scheduler or event router. n8n fills that gap: it watches for events (Slack messages, cron timers, HR webhooks), transforms payloads, calls the AegisMind API, and routes the results — all without any extra backend code.",
  },
  {
    icon: <Zap className="h-5 w-5 text-amber-400" />,
    title: "How are they connected?",
    body: "n8n runs as a Docker container on the same internal network as Agora (the AegisMind API server). Its workflows call http://agora:8000 directly — this means zero public internet exposure for API calls, and Zanzibar ACLs still enforce on every search request.",
  },
  {
    icon: <Settings2 className="h-5 w-5 text-emerald-400" />,
    title: "Can I customise workflows?",
    body: "Yes. Open the n8n UI, click any workflow, and drag-drop new nodes. All 6 pre-built workflows are a starting point. You can add Gmail, Google Drive, Jira, Salesforce, or any of n8n's 400+ built-in integrations with no code changes to AegisMind.",
  },
];

// ─── Helper: trigger a webhook workflow ───────────────────────────────────────

async function fireWebhook(path: string, body: unknown): Promise<{ ok: boolean; message: string }> {
  try {
    const res = await fetch(`${N8N_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) return { ok: true, message: "Workflow triggered successfully" };
    const text = await res.text();
    return { ok: false, message: `n8n returned ${res.status}: ${text.slice(0, 120)}` };
  } catch (err) {
    return { ok: false, message: `Could not reach n8n at ${N8N_BASE}. Is it running?` };
  }
}

// ─── Quick test payload map ────────────────────────────────────────────────────

function testPayloadFor(id: string): unknown {
  switch (id) {
    case "01":
      return {
        title: "Test Document from Lens UI",
        content:
          "This is a test document ingested via the n8n webhook from the AegisMind Lens interface.",
        tenant_id: "corp-default",
        allowed_users: ["alice", "bob"],
      };
    case "03":
      return {
        type: "url_verification",
        challenge: "lens-ui-test-ping",
      };
    case "06":
      return {
        event_type: "employee.onboarded",
        employee_id: "test-user-001",
        department: "engineering",
        role: "engineer",
        tenant_id: "corp-default",
      };
    default:
      return { source: "lens-ui", timestamp: new Date().toISOString() };
  }
}

// ─── WorkflowCard ─────────────────────────────────────────────────────────────

function WorkflowCard({ wf }: { wf: WorkflowDef }) {
  const [expanded, setExpanded] = React.useState(false);
  const [run, setRun] = React.useState<RunState>({ status: "idle" });

  const triggerWorkflow = async () => {
    if (!wf.webhookPath) return;
    setRun({ status: "running" });
    const result = await fireWebhook(wf.webhookPath, testPayloadFor(wf.id));
    setRun({ status: result.ok ? "success" : "error", message: result.message });
    setTimeout(() => setRun({ status: "idle" }), 4000);
  };

  const statusIcon = {
    idle: null,
    running: <RefreshCw className="h-3.5 w-3.5 animate-spin text-blue-400" />,
    success: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />,
    error: <X className="h-3.5 w-3.5 text-red-400" />,
  }[run.status];

  return (
    <Card className="border-border/60 bg-card/60 hover:border-primary/30 transition-all duration-200 overflow-hidden">
      <div className={`h-0.5 w-full bg-gradient-to-r ${wf.color}`} />
      <CardHeader className="pb-2 pt-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div
              className={`flex items-center justify-center h-9 w-9 rounded-lg bg-gradient-to-br ${wf.color} border border-white/5 text-foreground/80`}
            >
              {wf.icon}
            </div>
            <div>
              <CardTitle className="text-sm font-semibold leading-tight">
                {wf.title}
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                {wf.subtitle}
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Badge
              variant="outline"
              className="text-[10px] font-mono px-1.5 py-0.5 border-border/60 text-muted-foreground"
            >
              {wf.trigger === "schedule" ? (
                <Clock className="h-2.5 w-2.5 mr-1 inline" />
              ) : (
                <Zap className="h-2.5 w-2.5 mr-1 inline" />
              )}
              {wf.trigger}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pb-2 space-y-2">
        {/* Trigger label */}
        <div className="text-[11px] font-mono bg-muted/40 border border-border/40 rounded px-2 py-1 text-muted-foreground truncate">
          {wf.triggerLabel}
        </div>

        {/* Expandable description */}
        <button
          type="button"
          onClick={() => setExpanded((p) => !p)}
          className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors w-full text-left"
        >
          {expanded ? (
            <ChevronUp className="h-3 w-3 shrink-0" />
          ) : (
            <ChevronDown className="h-3 w-3 shrink-0" />
          )}
          {expanded ? "Hide details" : "How it works"}
        </button>

        {expanded && (
          <div className="space-y-2 pt-1">
            <p className="text-xs text-muted-foreground leading-relaxed">
              {wf.description}
            </p>
            <ol className="space-y-1">
              {wf.steps.map((step, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-foreground/80">
                  <span className="flex-shrink-0 h-4 w-4 rounded-full bg-primary/20 text-primary text-[10px] flex items-center justify-center font-bold mt-0.5">
                    {i + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </div>
        )}

        {/* Run status message */}
        {run.status !== "idle" && (
          <div
            className={`flex items-center gap-1.5 text-[11px] rounded px-2 py-1 border ${
              run.status === "success"
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                : run.status === "error"
                ? "bg-red-500/10 border-red-500/30 text-red-300"
                : "bg-blue-500/10 border-blue-500/30 text-blue-300"
            }`}
          >
            {statusIcon}
            {run.message || (run.status === "running" ? "Triggering…" : "")}
          </div>
        )}
      </CardContent>

      <CardFooter className="pt-2 pb-3 gap-2 flex flex-wrap">
        {/* Open in n8n */}
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs gap-1.5 border-border/60"
          onClick={() => window.open(`${N8N_BASE}/workflow`, "_blank")}
        >
          <ExternalLink className="h-3 w-3" />
          Edit in n8n
        </Button>

        {/* Test fire (webhook only) */}
        {wf.webhookPath && (
          <Button
            variant="default"
            size="sm"
            className="h-7 text-xs gap-1.5"
            disabled={run.status === "running"}
            onClick={triggerWorkflow}
          >
            {run.status === "running" ? (
              <RefreshCw className="h-3 w-3 animate-spin" />
            ) : (
              <Play className="h-3 w-3" />
            )}
            Test Fire
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}

// ─── Main Automation component ────────────────────────────────────────────────

export function Automation() {
  const [showEmbed, setShowEmbed] = React.useState(false);
  const [n8nOnline, setN8nOnline] = React.useState<boolean | null>(null);

  // Probe n8n health
  React.useEffect(() => {
    fetch(`${N8N_BASE}/healthz`, { signal: AbortSignal.timeout(3000) })
      .then((r) => setN8nOnline(r.ok))
      .catch(() => setN8nOnline(false));
  }, []);

  const statusDot =
    n8nOnline === null
      ? "bg-muted-foreground animate-pulse"
      : n8nOnline
      ? "bg-emerald-400"
      : "bg-amber-400";

  const statusText =
    n8nOnline === null
      ? "Checking n8n…"
      : n8nOnline
      ? "n8n online"
      : "n8n offline — start with docker compose up";

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-8">
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-violet-500/30 to-blue-500/10 border border-violet-500/30 flex items-center justify-center">
            <Workflow className="h-5 w-5 text-violet-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight">Automation</h1>
            <p className="text-xs text-muted-foreground">
              Powered by n8n · 6 pre-built workflows
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Status badge */}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground border border-border/60 rounded-lg px-3 py-1.5 bg-card/40">
            <span className={`h-2 w-2 rounded-full ${statusDot}`} />
            {statusText}
          </div>

          {/* Open n8n */}
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 text-xs h-8"
            onClick={() => window.open(N8N_BASE, "_blank")}
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open n8n UI
          </Button>

          {/* Embed toggle */}
          <Button
            variant={showEmbed ? "default" : "ghost"}
            size="sm"
            className="gap-1.5 text-xs h-8"
            onClick={() => setShowEmbed((p) => !p)}
          >
            <Settings2 className="h-3.5 w-3.5" />
            {showEmbed ? "Hide Embed" : "Embed n8n"}
          </Button>
        </div>
      </div>

      {/* ── Embedded n8n iFrame ── */}
      {showEmbed && (
        <div className="rounded-xl overflow-hidden border border-border/60 shadow-lg bg-card/30">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border/40 text-xs text-muted-foreground bg-card/60">
            <div className="flex items-center gap-2">
              <Workflow className="h-3.5 w-3.5 text-violet-400" />
              <span className="font-medium text-foreground">n8n Workflow Editor</span>
              <span className="text-border/60">—</span>
              <span className="font-mono text-[11px]">{N8N_BASE}</span>
            </div>
            <button
              type="button"
              onClick={() => setShowEmbed(false)}
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <iframe
            src={`${N8N_BASE}/`}
            title="n8n Workflow Editor"
            className="w-full"
            style={{ height: "600px", border: "none" }}
            allow="clipboard-read; clipboard-write"
          />
        </div>
      )}

      {/* ── What is n8n? ── */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
          What is n8n?
        </h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {CONCEPTS.map((c) => (
            <div
              key={c.title}
              className="rounded-xl border border-border/50 bg-card/50 p-4 hover:border-primary/30 transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <div className="h-7 w-7 rounded-lg bg-muted/60 flex items-center justify-center">
                  {c.icon}
                </div>
                <span className="text-xs font-semibold">{c.title}</span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">{c.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Data flow diagram ── */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
          How it fits together
        </h2>
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border/50 bg-card/40 px-5 py-4 text-xs font-mono overflow-x-auto">
          {[
            { label: "Slack / GitHub / HR", icon: <GitBranch className="h-3.5 w-3.5" /> },
            null,
            { label: "n8n :5678", icon: <Workflow className="h-3.5 w-3.5 text-violet-400" />, highlight: true },
            null,
            { label: "Agora :8000", icon: <Brain className="h-3.5 w-3.5 text-primary" /> },
            null,
            { label: "SpiceDB + pgvector", icon: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> },
          ].map((item, i) =>
            item === null ? (
              <ArrowRight key={i} className="h-4 w-4 text-muted-foreground/50 shrink-0" />
            ) : (
              <div
                key={i}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 border ${
                  item.highlight
                    ? "border-violet-500/40 bg-violet-500/10 text-violet-300"
                    : "border-border/60 bg-muted/30 text-foreground/80"
                }`}
              >
                {item.icon}
                {item.label}
              </div>
            )
          )}
          <span className="text-muted-foreground text-[11px] ml-auto">
            All calls are internal Docker network — no public exposure
          </span>
        </div>
      </section>

      {/* ── Workflow grid ── */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            Pre-built Workflows
          </h2>
          <Badge variant="outline" className="text-[11px] border-border/60 text-muted-foreground">
            {WORKFLOWS.length} workflows
          </Badge>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {WORKFLOWS.map((wf) => (
            <WorkflowCard key={wf.id} wf={wf} />
          ))}
        </div>
      </section>

      {/* ── Quick setup guide ── */}
      <section className="rounded-xl border border-border/50 bg-card/40 p-5 space-y-3">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-primary" />
          Quick Setup (5 minutes)
        </h2>
        <ol className="space-y-2">
          {[
            "Start the stack: docker compose up -d — this starts n8n on port 5678 alongside Agora",
            `Open n8n: ${N8N_BASE} — login with admin / (your N8N_BASIC_AUTH_PASSWORD from .env)`,
            "Go to Settings → Credentials → add your Slack API OAuth token",
            "Workflows are auto-imported from ./n8n/workflows/ — just activate each one",
            "For Slack bot: point your Slack App Event Subscriptions URL to the n8n webhook path shown above",
            "For HR provisioning: configure your HR system (BambooHR, Rippling, Workday) to POST to the ACL webhook",
          ].map((step, i) => (
            <li key={i} className="flex items-start gap-3 text-xs text-muted-foreground">
              <span className="flex-shrink-0 h-5 w-5 rounded-full bg-primary/15 text-primary text-[10px] flex items-center justify-center font-bold mt-0.5">
                {i + 1}
              </span>
              {step}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
