import * as React from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  getLocalToolActivity,
  clearLocalToolActivity,
  getLocalToolEventsUrl,
  type LocalToolActivityEvent,
} from "@/lib/api";
import {
  Terminal,
  Search,
  FileText,
  Clock,
  RefreshCw,
  FolderOpen,
  Filter,
  Play,
  Pause,
  Trash2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Layers,
  AlertTriangle,
  Loader2,
  CheckCircle2,
  XCircle,
  Shield,
  Activity,
} from "lucide-react";

type CategoryFilter = "all" | "filesystem" | "knowledge" | "sandbox" | "notes" | "system";
type StatusFilter = "all" | "running" | "success" | "failed";

export function LocalTools() {
  const [events, setEvents] = React.useState<LocalToolActivityEvent[]>([]);
  const [selectedCategory, setSelectedCategory] = React.useState<CategoryFilter>("all");
  const [selectedStatus, setSelectedStatus] = React.useState<StatusFilter>("all");
  const [searchQuery, setSearchQuery] = React.useState<string>("");
  const [isLoading, setIsLoading] = React.useState<boolean>(false);
  const [isPaused, setIsPaused] = React.useState<boolean>(false);
  const [isLiveConnected, setIsLiveConnected] = React.useState<boolean>(false);
  const [expandedEventIds, setExpandedEventIds] = React.useState<Set<string>>(new Set());

  const isJiraOrConfluence = React.useCallback((evt: LocalToolActivityEvent) => {
    const name = (evt.tool_name || "").toLowerCase();
    const params = JSON.stringify(evt.parameters || {}).toLowerCase();
    return (
      name.includes("jira") ||
      name.includes("confluence") ||
      params.includes("jira") ||
      params.includes("confluence")
    );
  }, []);

  // Fetch historical activity from backend
  const fetchEvents = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await getLocalToolActivity(
        selectedCategory === "all" ? undefined : selectedCategory,
        selectedStatus === "all" ? undefined : selectedStatus,
        100
      );
      // Filter out JIRA_SYNC and CONFLUENCE_SYNC
      setEvents(data.filter((e) => !isJiraOrConfluence(e)));
    } catch {
      // Offline or network error handled gracefully
    } finally {
      setIsLoading(false);
    }
  }, [selectedCategory, selectedStatus, isJiraOrConfluence]);

  React.useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  // Real-time Server-Sent Events (SSE) subscription
  React.useEffect(() => {
    let eventSource: EventSource | null = null;
    let isMounted = true;

    try {
      const sseUrl = getLocalToolEventsUrl();
      eventSource = new EventSource(sseUrl);

      eventSource.onopen = () => {
        if (isMounted) {
          setIsLiveConnected(true);
        }
      };

      eventSource.onmessage = (messageEvent) => {
        if (!isMounted || isPaused) return;

        try {
          const rawData = messageEvent.data;
          if (!rawData || rawData.startsWith(":")) return;

          const newEvt: LocalToolActivityEvent = JSON.parse(rawData);

          // Strip out Jira & Confluence sync events
          if (isJiraOrConfluence(newEvt)) return;

          setEvents((prev) => {
            const index = prev.findIndex((e) => e.event_id === newEvt.event_id);
            if (index >= 0) {
              // Update running event to completed (success/failed) in place
              const updated = [...prev];
              updated[index] = newEvt;
              return updated;
            }
            // Prepend new event to keep chronological order
            return [newEvt, ...prev].slice(0, 150);
          });
        } catch {
          // Ignore parse errors on heartbeat
        }
      };

      eventSource.onerror = () => {
        if (isMounted) {
          setIsLiveConnected(false);
        }
      };
    } catch {
      setIsLiveConnected(false);
    }

    return () => {
      isMounted = false;
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [isPaused, isJiraOrConfluence]);

  // Handle clear activity
  const handleClearActivity = async () => {
    const confirmed = window.confirm("Are you sure you want to clear the local tool activity ledger?");
    if (!confirmed) return;
    const ok = await clearLocalToolActivity();
    if (ok) {
      setEvents([]);
      setExpandedEventIds(new Set());
    }
  };

  // Toggle card expansion
  const toggleExpand = (eventId: string) => {
    setExpandedEventIds((prev) => {
      const next = new Set(prev);
      if (next.has(eventId)) {
        next.delete(eventId);
      } else {
        next.add(eventId);
      }
      return next;
    });
  };

  // Filtered events
  const filteredEvents = React.useMemo(() => {
    return events.filter((evt) => {
      if (isJiraOrConfluence(evt)) {
        return false;
      }
      if (selectedCategory !== "all" && evt.category.toLowerCase() !== selectedCategory) {
        return false;
      }
      if (selectedStatus !== "all" && evt.status.toLowerCase() !== selectedStatus) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = evt.tool_name.toLowerCase().includes(q);
        const matchesAgent = evt.agent_id.toLowerCase().includes(q);
        const matchesSummary = (evt.result_summary || "").toLowerCase().includes(q);
        const matchesParams = JSON.stringify(evt.parameters || {}).toLowerCase().includes(q);
        return matchesName || matchesAgent || matchesSummary || matchesParams;
      }
      return true;
    });
  }, [events, selectedCategory, selectedStatus, searchQuery, isJiraOrConfluence]);

  // Icon mapping for categories
  const getToolIcon = (_toolName: string, category: string) => {
    switch (category) {
      case "knowledge":
        return <Search className="h-4 w-4 text-sky-400" />;
      case "filesystem":
        return <FileText className="h-4 w-4 text-emerald-400" />;
      case "notes":
        return <FolderOpen className="h-4 w-4 text-amber-400" />;
      case "sandbox":
        return <Terminal className="h-4 w-4 text-purple-400" />;
      default:
        return <Cpu className="h-4 w-4 text-primary" />;
    }
  };

  // Category counts
  const categoryCounts = React.useMemo(() => {
    const active = events.filter((e) => !isJiraOrConfluence(e));
    const counts: Record<string, number> = {
      all: active.length,
      filesystem: 0,
      knowledge: 0,
      sandbox: 0,
      notes: 0,
      system: 0,
    };
    active.forEach((e) => {
      const cat = e.category.toLowerCase();
      if (cat in counts) {
        counts[cat] = (counts[cat] || 0) + 1;
      } else {
        counts.system = (counts.system || 0) + 1;
      }
    });
    return counts;
  }, [events, isJiraOrConfluence]);

  return (
    <div className="flex-1 p-4 sm:p-6 max-w-7xl mx-auto w-full space-y-6">
      {/* Top Header Card — Styled with the exact menu section background format */}
      <div className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl p-5 shadow-xl space-y-4 text-foreground transition-colors">
        {/* Header Title & Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 dark:border-white/10 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
                <Terminal className="h-6 w-6 text-primary" />
                Local Agent Tools Activity
              </h1>
              <Badge variant="outline" className="border-primary/40 text-primary text-xs">
                Live Transparency Feed
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Real-time auditable ledger of all local tool invocations executed autonomously on this sovereign system.
            </p>
          </div>

          {/* Live status and Controls */}
          <div className="flex flex-wrap items-center gap-2">
            {/* LIVE indicator */}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium transition-colors border ${
                isPaused
                  ? "bg-amber-500/10 border-amber-500/30 text-amber-500"
                  : isLiveConnected
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-500"
                  : "bg-muted/40 border-border text-muted-foreground"
              }`}
            >
              {isPaused ? (
                <>
                  <span className="h-2 w-2 rounded-full bg-amber-400" />
                  <span>PAUSED</span>
                </>
              ) : isLiveConnected ? (
                <>
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                  </span>
                  <span>LIVE STREAMING</span>
                </>
              ) : (
                <>
                  <span className="h-2 w-2 rounded-full bg-muted-foreground/60" />
                  <span>OFFLINE POLLING</span>
                </>
              )}
            </div>

            {/* Pause / Resume Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsPaused((prev) => !prev)}
              className="text-xs flex items-center gap-1.5 h-8 bg-transparent"
            >
              {isPaused ? (
                <>
                  <Play className="h-3.5 w-3.5 text-emerald-500" />
                  <span>Resume Feed</span>
                </>
              ) : (
                <>
                  <Pause className="h-3.5 w-3.5 text-amber-500" />
                  <span>Pause Feed</span>
                </>
              )}
            </Button>

            {/* Refresh Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={fetchEvents}
              disabled={isLoading}
              className="text-xs flex items-center gap-1.5 h-8 bg-transparent"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin text-primary" : ""}`} />
              <span>Refresh</span>
            </Button>

            {/* Clear Activity Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={handleClearActivity}
              disabled={events.length === 0}
              className="text-xs flex items-center gap-1.5 h-8 text-rose-500 hover:text-rose-600 dark:text-rose-400 dark:hover:text-rose-300 hover:border-rose-500/40 bg-transparent"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>Clear</span>
            </Button>
          </div>
        </div>

        {/* Control Bar: Filters & Search */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pt-1">
          {/* Category Filters */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground flex items-center gap-1 mr-1 font-medium">
              <Filter className="h-3 w-3" /> Category:
            </span>
            {(
              [
                { id: "all", label: "All" },
                { id: "filesystem", label: "Filesystem" },
                { id: "knowledge", label: "Knowledge" },
                { id: "sandbox", label: "Sandbox" },
                { id: "notes", label: "Notes" },
                { id: "system", label: "System" },
              ] as const
            ).map((cat) => {
              const count = categoryCounts[cat.id] || 0;
              const isSelected = selectedCategory === cat.id;
              return (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => setSelectedCategory(cat.id)}
                  className={`text-[11px] px-2.5 py-1 rounded-lg border transition-colors flex items-center gap-1.5 ${
                    isSelected
                      ? "bg-primary text-primary-foreground border-primary font-medium shadow-xs"
                      : "bg-slate-100/80 dark:bg-white/5 text-muted-foreground border-slate-200 dark:border-white/10 hover:text-foreground"
                  }`}
                >
                  <span>{cat.label}</span>
                  <span
                    className={`text-[9px] px-1 py-0.2 rounded-full ${
                      isSelected
                        ? "bg-primary-foreground/20 text-primary-foreground"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Status Filter and Search */}
          <div className="flex items-center gap-2">
            {/* Status selector */}
            <div className="flex items-center gap-1 text-[11px] bg-slate-100/80 dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-lg p-0.5">
              {(
                [
                  { id: "all", label: "All Status" },
                  { id: "success", label: "Success" },
                  { id: "running", label: "Running" },
                  { id: "failed", label: "Failed" },
                ] as const
              ).map((st) => (
                <button
                  key={st.id}
                  type="button"
                  onClick={() => setSelectedStatus(st.id)}
                  className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                    selectedStatus === st.id
                      ? "bg-white dark:bg-white/15 text-foreground font-semibold shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {st.label}
                </button>
              ))}
            </div>

            {/* Quick search input */}
            <div className="relative">
              <Search className="h-3 w-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search actions..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="text-xs pl-7 pr-2.5 py-1 rounded-lg bg-slate-100/80 dark:bg-white/5 border border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary w-36 sm:w-48"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Event Timeline Cards */}
      <div className="space-y-3">
        {filteredEvents.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 dark:border-white/15 bg-white/90 dark:bg-[#141826]/80 p-10 text-center shadow-sm">
            <Terminal className="h-8 w-8 mx-auto text-muted-foreground/60 mb-2" />
            <p className="text-xs font-semibold text-foreground">No local tool calls recorded yet</p>
            <p className="text-[11px] text-muted-foreground mt-1 max-w-md mx-auto">
              When the sovereign agent searches offline vector knowledge, inspects system files, records notes, or runs sandboxed diagnostic commands, every execution is recorded here live with duration and parameters.
            </p>
          </div>
        ) : (
          filteredEvents.map((evt) => {
            const isExpanded = expandedEventIds.has(evt.event_id);
            const isRunning = evt.status === "running";
            const isSuccess = evt.status === "success";
            const isFailed = evt.status === "failed";

            return (
              <div
                key={evt.event_id}
                className={`rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-md overflow-hidden transition-all hover:border-primary/40 ${
                  isRunning ? "border-sky-500/40" : isFailed ? "border-rose-500/30" : ""
                }`}
              >
                {/* Clickable Header for expansion */}
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleExpand(evt.event_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      toggleExpand(evt.event_id);
                    }
                  }}
                  className="py-3 px-4 bg-muted/10 border-b border-border/40 cursor-pointer select-none flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-muted/20 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-md bg-secondary/80 border border-border/60">
                      {getToolIcon(evt.tool_name, evt.category)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs font-bold text-foreground">
                          {evt.tool_name}
                        </span>
                        <Badge
                          variant="outline"
                          className="text-[9px] uppercase tracking-wider py-0 px-1.5 border-border bg-secondary/50 font-mono"
                        >
                          {evt.category}
                        </Badge>
                        <Badge
                          variant="outline"
                          className="text-[9px] py-0 px-1.5 border-primary/30 text-primary bg-primary/5 font-mono flex items-center gap-1"
                        >
                          <Shield className="h-2.5 w-2.5" />
                          Sovereign Local
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 text-[10px] text-muted-foreground">
                        <span>Agent: {evt.agent_id}</span>
                        <span>•</span>
                        <span>Source: {evt.source}</span>
                      </div>
                    </div>
                  </div>

                  {/* Status, Duration, Timestamp, Expand Chevron */}
                  <div className="flex items-center gap-3">
                    {/* Status badge */}
                    {isRunning ? (
                      <Badge
                        variant="outline"
                        className="bg-sky-500/10 text-sky-400 border-sky-500/30 text-[10px] flex items-center gap-1 animate-pulse"
                      >
                        <Loader2 className="h-3 w-3 animate-spin" /> Running
                      </Badge>
                    ) : isSuccess ? (
                      <Badge
                        variant="outline"
                        className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30 text-[10px] flex items-center gap-1"
                      >
                        <CheckCircle2 className="h-3 w-3" /> Success
                      </Badge>
                    ) : (
                      <Badge
                        variant="outline"
                        className="bg-rose-500/10 text-rose-400 border-rose-500/30 text-[10px] flex items-center gap-1"
                      >
                        <XCircle className="h-3 w-3" /> Failed
                      </Badge>
                    )}

                    {/* Execution Duration */}
                    <span className="text-[10px] text-foreground font-mono bg-secondary/60 px-2 py-0.5 rounded border border-border/50">
                      {isRunning ? "..." : `${evt.duration_ms.toFixed(1)} ms`}
                    </span>

                    {/* Timestamp */}
                    <span className="text-[10px] text-muted-foreground flex items-center gap-1 font-mono">
                      <Clock className="h-3 w-3 text-muted-foreground/80" />
                      {new Date(evt.timestamp).toLocaleTimeString()}
                    </span>

                    {/* Expand icon */}
                    <div className="text-muted-foreground">
                      {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </div>
                  </div>
                </div>

                {/* Card Summary Line */}
                <div className="p-3 text-xs space-y-2">
                  {/* Sanitized Parameters Summary */}
                  {evt.parameters && Object.keys(evt.parameters).length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                      <span className="text-muted-foreground font-medium text-[10px]">Params:</span>
                      {Object.entries(evt.parameters).slice(0, 3).map(([k, v]) => (
                        <span
                          key={k}
                          className="bg-secondary/70 border border-border/60 px-2 py-0.5 rounded font-mono text-[10px] text-foreground inline-flex items-center gap-1"
                        >
                          <span className="text-muted-foreground">{k}:</span>
                          <span className="max-w-xs truncate">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                        </span>
                      ))}
                      {Object.keys(evt.parameters).length > 3 && (
                        <span className="text-[10px] text-muted-foreground">
                          +{Object.keys(evt.parameters).length - 3} more
                        </span>
                      )}
                    </div>
                  )}

                  {/* Result Summary snippet */}
                  {evt.result_summary && !isExpanded && (
                    <div className="text-[11px] text-muted-foreground font-mono bg-background/40 p-2 rounded border border-border/40 line-clamp-2">
                      {evt.result_summary}
                    </div>
                  )}

                  {/* Error if failed */}
                  {evt.error && !isExpanded && (
                    <div className="text-[11px] text-rose-400 font-mono bg-rose-500/5 p-2 rounded border border-rose-500/20 flex items-start gap-1.5">
                      <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                      <span className="line-clamp-2">{evt.error}</span>
                    </div>
                  )}
                </div>

                {/* Expanded Details Section */}
                {isExpanded && (
                  <CardContent className="px-4 pb-4 pt-1 border-t border-border/40 bg-secondary/10 space-y-3 text-xs">
                    {/* Grid metadata */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
                      <div className="p-2 rounded bg-background/50 border border-border/50">
                        <span className="text-[10px] text-muted-foreground block">Execution Status</span>
                        <span className="font-mono text-xs font-semibold capitalize flex items-center gap-1 mt-0.5">
                          {isSuccess && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />}
                          {isFailed && <XCircle className="h-3.5 w-3.5 text-rose-400" />}
                          {isRunning && <Loader2 className="h-3.5 w-3.5 text-sky-400 animate-spin" />}
                          {evt.status}
                        </span>
                      </div>
                      <div className="p-2 rounded bg-background/50 border border-border/50">
                        <span className="text-[10px] text-muted-foreground block">Execution Duration</span>
                        <span className="font-mono text-xs font-semibold text-foreground block mt-0.5">
                          {evt.duration_ms.toFixed(2)} ms
                        </span>
                      </div>
                      <div className="p-2 rounded bg-background/50 border border-border/50">
                        <span className="text-[10px] text-muted-foreground block">Approval Required</span>
                        <span className="font-mono text-xs font-semibold text-foreground block mt-0.5">
                          {evt.approval_required ? "Yes (Write/Execute)" : "No (Autonomous Safe)"}
                        </span>
                      </div>
                      <div className="p-2 rounded bg-background/50 border border-border/50">
                        <span className="text-[10px] text-muted-foreground block">Execution Mode</span>
                        <span className="font-mono text-xs font-semibold text-foreground block mt-0.5">
                          100% Offline Air-Gapped
                        </span>
                      </div>
                    </div>

                    {/* Sanitized Parameters Full View */}
                    <div>
                      <span className="text-[11px] font-semibold text-foreground flex items-center gap-1 mb-1">
                        <Layers className="h-3.5 w-3.5 text-primary" /> Sanitized Input Parameters:
                      </span>
                      <pre className="bg-background/80 p-3 rounded border border-border/60 font-mono text-[11px] overflow-x-auto text-foreground">
                        {JSON.stringify(evt.parameters, null, 2)}
                      </pre>
                    </div>

                    {/* Full Result Summary */}
                    {evt.result_summary && (
                      <div>
                        <span className="text-[11px] font-semibold text-foreground flex items-center gap-1 mb-1">
                          <Activity className="h-3.5 w-3.5 text-emerald-400" /> Result Summary:
                        </span>
                        <div className="bg-background/80 p-3 rounded border border-border/60 font-mono text-[11px] text-muted-foreground whitespace-pre-wrap max-h-48 overflow-y-auto">
                          {evt.result_summary}
                        </div>
                      </div>
                    )}

                    {/* Error message */}
                    {evt.error && (
                      <div>
                        <span className="text-[11px] font-semibold text-rose-400 flex items-center gap-1 mb-1">
                          <AlertTriangle className="h-3.5 w-3.5 text-rose-400" /> Failure Information:
                        </span>
                        <div className="bg-rose-500/10 p-3 rounded border border-rose-500/30 font-mono text-[11px] text-rose-300 whitespace-pre-wrap">
                          {evt.error}
                        </div>
                      </div>
                    )}
                  </CardContent>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
