import * as React from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardContent,
} from "@/components/ui/card";
import { listAgentTools, type AgentToolEvent } from "@/lib/api";
import {
  Terminal,
  ShieldCheck,
  ShieldAlert,
  Search,
  FileText,
  Clock,
  RefreshCw,
  FolderOpen,
  Filter,
} from "lucide-react";

export function LocalTools() {
  const [events, setEvents] = React.useState<AgentToolEvent[]>([]);
  const [selectedTool, setSelectedTool] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);

  const fetchEvents = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listAgentTools();
      setEvents(data);
    } catch {
      // Ignored
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const uniqueTools = React.useMemo(() => {
    const set = new Set<string>();
    events.forEach((e) => {
      const toolName = e.action.replace("invoke_", "");
      set.add(toolName);
    });
    return Array.from(set);
  }, [events]);

  const filteredEvents = React.useMemo(() => {
    if (!selectedTool) return events;
    return events.filter((e) => e.action.includes(selectedTool));
  }, [events, selectedTool]);

  const getToolIcon = (action: string) => {
    if (action.includes("search")) return <Search className="h-4 w-4 text-sky-400" />;
    if (action.includes("read")) return <FileText className="h-4 w-4 text-emerald-400" />;
    if (action.includes("note")) return <FolderOpen className="h-4 w-4 text-amber-400" />;
    return <Terminal className="h-4 w-4 text-purple-400" />;
  };

  return (
    <div className="flex-1 p-6 max-w-7xl mx-auto w-full space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/70 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
              <Terminal className="h-6 w-6 text-primary" />
              Local Agent Tools Activity
            </h1>
            <Badge variant="outline" className="border-primary/40 text-primary text-xs">
              Live Transparency Feed
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Real-time auditable ledger of all local tool invocations executed autonomously on this system.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchEvents}
            disabled={isLoading}
            className="text-xs flex items-center gap-1.5"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin text-primary" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Filter Chips */}
      {uniqueTools.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 pb-2">
          <span className="text-[11px] text-muted-foreground flex items-center gap-1 mr-1">
            <Filter className="h-3 w-3" /> Filter Tool:
          </span>
          <button
            type="button"
            onClick={() => setSelectedTool(null)}
            className={`text-[11px] px-2.5 py-1 rounded-md border transition-colors ${
              selectedTool === null
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-muted/30 text-muted-foreground border-border hover:bg-muted"
            }`}
          >
            All Actions ({events.length})
          </button>
          {uniqueTools.map((tool) => (
            <button
              key={tool}
              type="button"
              onClick={() => setSelectedTool(tool === selectedTool ? null : tool)}
              className={`text-[11px] px-2.5 py-1 rounded-md border transition-colors ${
                selectedTool === tool
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-muted/30 text-muted-foreground border-border hover:bg-muted"
              }`}
            >
              {tool}
            </button>
          ))}
        </div>
      )}

      {/* Event Timeline */}
      <div className="space-y-3">
        {filteredEvents.length === 0 ? (
          <Card className="border-dashed border-border/80 bg-muted/10 p-10 text-center">
            <Terminal className="h-8 w-8 mx-auto text-muted-foreground/60 mb-2" />
            <p className="text-xs font-semibold text-foreground">No local tool calls recorded yet</p>
            <p className="text-[11px] text-muted-foreground mt-1">
              When the sovereign agent reads files, inspects logs, runs sandboxed diagnostics, or creates notes, every action is logged here.
            </p>
          </Card>
        ) : (
          filteredEvents.map((evt) => {
            const isRejected = evt.action.includes("rejected");
            const isSuccess = evt.metadata?.success !== false && !isRejected;
            const toolName = evt.action.replace("invoke_", "");

            return (
              <Card
                key={evt.id}
                className="border-border/70 bg-card/40 backdrop-blur-sm overflow-hidden transition-all hover:bg-card/70"
              >
                <CardHeader className="py-3 px-4 bg-muted/10 border-b border-border/50">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div className="p-1.5 rounded-md bg-secondary/80 border border-border/60">
                        {getToolIcon(toolName)}
                      </div>
                      <div>
                        <span className="font-mono text-xs font-bold text-foreground">
                          {toolName}
                        </span>
                        <span className="text-[10px] text-muted-foreground ml-2">
                          Caller: {evt.principal_id}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {isSuccess ? (
                        <Badge
                          variant="outline"
                          className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30 text-[10px] flex items-center gap-1"
                        >
                          <ShieldCheck className="h-3 w-3" /> Allowed & Executed
                        </Badge>
                      ) : (
                        <Badge
                          variant="outline"
                          className="bg-rose-500/10 text-rose-400 border-rose-500/30 text-[10px] flex items-center gap-1"
                        >
                          <ShieldAlert className="h-3 w-3" /> Sandboxed / Denied
                        </Badge>
                      )}
                      <span className="text-[10px] text-muted-foreground flex items-center gap-1 font-mono">
                        <Clock className="h-3 w-3" />
                        {new Date(evt.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="p-4 space-y-2 text-xs">
                  {/* Arguments or Command */}
                  {evt.metadata?.command && (
                    <div className="flex items-start gap-2 bg-muted/30 p-2.5 rounded border border-border/40 font-mono text-[11px]">
                      <span className="text-muted-foreground font-semibold">cmd:</span>
                      <span className="text-foreground">{evt.metadata.command}</span>
                    </div>
                  )}

                  {evt.metadata?.arguments && Object.keys(evt.metadata.arguments).length > 0 && (
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="text-muted-foreground font-semibold">Args:</span>
                      {Object.entries(evt.metadata.arguments).map(([k, v]) => (
                        <span
                          key={k}
                          className="bg-secondary/70 border border-border/60 px-2 py-0.5 rounded font-mono text-foreground"
                        >
                          {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Summary / Excerpt */}
                  {(evt.metadata?.result_summary || evt.metadata?.output_excerpt) && (
                    <div className="text-[11px] text-muted-foreground bg-background/50 p-2.5 rounded border border-border/40 font-mono line-clamp-3">
                      {evt.metadata.result_summary || evt.metadata.output_excerpt}
                    </div>
                  )}

                  {/* Reason for rejection if applicable */}
                  {evt.metadata?.reason && (
                    <div className="text-[11px] text-rose-400 font-mono">
                      Reason: {evt.metadata.reason}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}
