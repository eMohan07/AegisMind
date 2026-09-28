import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import {
  Brain,
  Search,
  Trash2,
  Clock,
  Loader2,
  Check,
  X,
  Shield,
  ChevronDown,
  ChevronRight,
  Sparkles,
  BookOpen,
  Settings2,
  Heart,
  RefreshCw,
  MessageSquare,
  Send,
  Bot,
  User,
  ExternalLink,
  Layers,
  CheckCircle2,
} from "lucide-react";
import {
  listMemoryRecords,
  approveMemory,
  rejectMemory,
  forgetMemory,
  getMemoryAudit,
  streamChat,
  type MemoryRecord,
  type MemoryStatusType,
  type MemoryType,
  type MemoryAuditEvent,
} from "@/lib/api";
import {
  getAllConversations,
  clearThread,
  clearAllConversations,
  recordExchange,
  subscribeToStore,
  type ConvThread,
  type ConvMessage,
} from "@/lib/conversationStore";

interface MemoryProps {
  currentUserId: string;
  currentTenantId: string;
  onNavigateToChat?: (query: string) => void;
}

type MainViewTab = "conversations" | "records";
type StatusTab = "all" | "active" | "pending";
type TypeFilter = "all" | MemoryType;

const TYPE_COLORS: Record<string, string> = {
  semantic: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
  episodic: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  procedural: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
  preference: "bg-violet-500/10 text-violet-600 dark:text-violet-400 border-violet-500/20",
};

const TYPE_ICONS: Record<string, React.ElementType> = {
  semantic: Brain,
  episodic: Clock,
  procedural: Settings2,
  preference: Heart,
};

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20",
  pending: "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/20",
  rejected: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20",
  forgotten: "bg-gray-500/10 text-gray-500 dark:text-gray-400 border-gray-500/20",
  superseded: "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20",
};

function timeAgo(dateStr: string): string {
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now.getTime() - then.getTime();
  if (isNaN(diffMs)) return "recently";
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return then.toLocaleDateString();
}

/* ---- MemoryCard for Knowledge Facts ---- */
function MemoryCard({
  memory,
  onApprove,
  onReject,
  onForget,
}: {
  memory: MemoryRecord;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onForget: (id: string) => void;
}) {
  const [expanded, setExpanded] = React.useState(false);
  const [auditLog, setAuditLog] = React.useState<MemoryAuditEvent[]>([]);
  const [loadingAudit, setLoadingAudit] = React.useState(false);

  const TypeIcon = TYPE_ICONS[memory.type] ?? Brain;

  const handleToggleAudit = async () => {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setLoadingAudit(true);
    try {
      const events = await getMemoryAudit(memory.id);
      setAuditLog(events);
    } catch {
      setAuditLog([]);
    }
    setLoadingAudit(false);
    setExpanded(true);
  };

  return (
    <Card className="group transition-all hover:shadow-xl rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-md">
      <CardContent className="p-4 space-y-3">
        {/* Header row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <TypeIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
            <Badge variant="outline" className={`text-xs ${TYPE_COLORS[memory.type] ?? ""}`}>
              {memory.type}
            </Badge>
            <Badge variant="outline" className={`text-xs ${STATUS_COLORS[memory.status] ?? ""}`}>
              {memory.status}
            </Badge>
            <span className="text-xs text-muted-foreground">{timeAgo(memory.created_at)}</span>
          </div>
          {memory.pinned && (
            <Badge variant="secondary" className="text-xs shrink-0">
              Pinned
            </Badge>
          )}
        </div>

        {/* Content */}
        <p className="text-sm font-medium text-foreground leading-relaxed">{memory.content}</p>

        {/* Entities */}
        {memory.entities && memory.entities.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {memory.entities.map((e, i) => (
              <Badge key={i} variant="secondary" className="text-xs font-normal">
                {e}
              </Badge>
            ))}
          </div>
        )}

        {/* Importance + confidence bar */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>Importance: {(memory.importance * 100).toFixed(0)}%</span>
          <span>Confidence: {(memory.confidence * 100).toFixed(0)}%</span>
          {memory.access_count > 0 && <span>Accessed: {memory.access_count}x</span>}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 pt-1">
          {memory.status === "pending" && (
            <>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs gap-1 text-green-600 hover:bg-green-500/10"
                onClick={() => onApprove(memory.id)}
              >
                <Check className="h-3 w-3" /> Approve
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs gap-1 text-red-600 hover:bg-red-500/10"
                onClick={() => onReject(memory.id)}
              >
                <X className="h-3 w-3" /> Reject
              </Button>
            </>
          )}
          {memory.status === "active" && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs gap-1 text-red-600 hover:bg-red-500/10"
              onClick={() => onForget(memory.id)}
            >
              <Trash2 className="h-3 w-3" /> Forget
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs gap-1 ml-auto"
            onClick={handleToggleAudit}
          >
            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            Audit
          </Button>
        </div>

        {/* Audit trail */}
        {expanded && (
          <div className="border-t pt-2 mt-1 space-y-1">
            {loadingAudit ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading audit trail...
              </div>
            ) : auditLog.length === 0 ? (
              <p className="text-xs text-muted-foreground">No audit events found.</p>
            ) : (
              auditLog.map((ev) => (
                <div key={ev.seq} className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-mono text-[10px] opacity-60">#{ev.seq}</span>
                  <Badge variant="outline" className="text-[10px] py-0">
                    {ev.event}
                  </Badge>
                  <span>{timeAgo(ev.ts)}</span>
                  <span className="ml-auto font-mono text-[10px] opacity-40 truncate max-w-[120px]">
                    {ev.hash.slice(0, 12)}...
                  </span>
                </div>
              ))
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ---- Individual Conversation Card sub-component ---- */
function ConversationCard({
  thread,
  onDelete,
}: {
  thread: ConvThread;
  onDelete: (id: string) => void;
}) {
  const [isExpanded, setIsExpanded] = React.useState(false);

  const sourceBadge = () => {
    switch (thread.source) {
      case "home":
        return <Badge variant="outline" className="text-[10px] border-cyan-500/40 text-cyan-400">Main Chat</Badge>;
      case "dataset":
        return <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-400">Dataset Chat</Badge>;
      case "notes":
        return <Badge variant="outline" className="text-[10px] border-purple-500/40 text-purple-400">Study Hub</Badge>;
      default:
        return <Badge variant="outline" className="text-[10px] border-blue-500/40 text-blue-400">Direct Chat</Badge>;
    }
  };

  return (
    <Card className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-md transition-all hover:shadow-lg">
      <CardContent className="p-4 space-y-3">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1 min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              {sourceBadge()}
              <span className="text-[11px] text-muted-foreground flex items-center gap-1 font-mono">
                <Clock className="h-3 w-3" />
                {timeAgo(thread.updatedAt)}
              </span>
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 font-mono">
                {thread.messages.length} {thread.messages.length === 1 ? "msg" : "msgs"}
              </Badge>
            </div>
            <h3 className="font-bold text-sm text-foreground truncate cursor-pointer" onClick={() => setIsExpanded(!isExpanded)}>
              {thread.label || "Untitled Conversation"}
            </h3>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground gap-1"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              <span>{isExpanded ? "Collapse" : "View"}</span>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
              onClick={() => onDelete(thread.threadId)}
              title="Delete conversation from memory"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* Message preview snippet if collapsed */}
        {!isExpanded && thread.messages.length > 0 && (
          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
            {thread.messages[thread.messages.length - 1]?.content || ""}
          </p>
        )}

        {/* Expanded Transcript */}
        {isExpanded && (
          <div className="border-t border-border/40 pt-3 mt-2 space-y-3 max-h-[400px] overflow-y-auto pr-1">
            {thread.messages.map((msg, idx) => (
              <div
                key={msg.id || idx}
                className={`p-3 rounded-xl text-xs leading-relaxed ${
                  msg.role === "user"
                    ? "bg-primary/10 border border-primary/20 text-foreground ml-4"
                    : "bg-muted/40 border border-border/50 text-foreground/90 mr-4"
                }`}
              >
                <div className="flex items-center justify-between font-semibold mb-1 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    {msg.role === "user" ? <User className="h-3 w-3 text-primary" /> : <Bot className="h-3 w-3 text-cyan-400" />}
                    {msg.role === "user" ? "User" : "Sovereign AI"}
                  </span>
                  <span className="font-mono text-[10px] opacity-70">
                    {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ""}
                  </span>
                </div>
                <div className="whitespace-pre-wrap">{msg.content}</div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ---- Main Memory Component ---- */
export function Memory({ currentUserId, currentTenantId, onNavigateToChat }: MemoryProps) {
  const [mainTab, setMainTab] = React.useState<MainViewTab>("conversations");
  const [conversations, setConversations] = React.useState<ConvThread[]>([]);
  const [records, setRecords] = React.useState<MemoryRecord[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [statusTab, setStatusTab] = React.useState<StatusTab>("all");
  const [typeFilter, setTypeFilter] = React.useState<TypeFilter>("all");
  const [searchQuery, setSearchQuery] = React.useState("");

  // Direct AI Interaction in Memory Section State
  const [directPrompt, setDirectPrompt] = React.useState("");
  const [isAiStreaming, setIsAiStreaming] = React.useState(false);
  const [directStreamText, setDirectStreamText] = React.useState("");
  const [directThinking, setDirectThinking] = React.useState<string | null>(null);

  // Load conversations from cross-chatbox store
  const loadConversations = React.useCallback(() => {
    const list = getAllConversations();
    setConversations(list);
  }, []);

  React.useEffect(() => {
    loadConversations();
    const unsubscribe = subscribeToStore(loadConversations);
    return () => unsubscribe();
  }, [loadConversations]);

  // Load memory records from API
  const fetchRecords = React.useCallback(async () => {
    setLoading(true);
    try {
      const statusParam: MemoryStatusType | undefined =
        statusTab === "all" ? undefined : (statusTab as MemoryStatusType);
      const typeParam: MemoryType | undefined =
        typeFilter === "all" ? undefined : (typeFilter as MemoryType);
      const data = await listMemoryRecords("global", statusParam, typeParam, 200);
      setRecords(data);
    } catch {
      setRecords([]);
    }
    setLoading(false);
  }, [statusTab, typeFilter]);

  React.useEffect(() => {
    if (mainTab === "records") {
      fetchRecords();
    }
  }, [mainTab, fetchRecords]);

  // Direct AI chat submission right inside the Memory section
  const handleDirectAiSend = async () => {
    const q = directPrompt.trim();
    if (!q || isAiStreaming) return;

    setDirectPrompt("");
    setIsAiStreaming(true);
    setDirectStreamText("");
    setDirectThinking("Accessing sovereign retrieval memory...");

    const userMsgId = `mem-user-${Date.now()}`;
    const asstMsgId = `mem-asst-${Date.now()}`;
    const threadId = `mem-${Date.now()}`;
    const threadLabel = q.length > 50 ? q.slice(0, 50) + "..." : q;

    let accumulated = "";

    try {
      streamChat({
        query: q,
        user_id: currentUserId,
        tenant_id: currentTenantId,
        onThinking: (status) => setDirectThinking(status),
        onToken: (token) => {
          accumulated += token;
          setDirectStreamText((prev) => prev + token);
        },
        onCitations: () => {},
        onDone: () => {
          setIsAiStreaming(false);
          setDirectThinking(null);
          // Persist directly as an individual conversation
          if (accumulated.trim()) {
            recordExchange({
              threadId,
              label: threadLabel,
              source: "home",
              userMessage: {
                id: userMsgId,
                content: q,
                timestamp: new Date().toISOString(),
              },
              assistantMessage: {
                id: asstMsgId,
                content: accumulated,
                timestamp: new Date().toISOString(),
              },
            });
            loadConversations();
          }
        },
        onError: (err) => {
          setIsAiStreaming(false);
          setDirectThinking(null);
          setDirectStreamText(`Error: ${err.message}`);
        },
      });
    } catch (err: any) {
      setIsAiStreaming(false);
      setDirectThinking(null);
      setDirectStreamText(`Failed to dispatch query: ${err?.message || err}`);
    }
  };

  // Filter conversations by search query
  const filteredConversations = React.useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const q = searchQuery.toLowerCase();
    return conversations.filter(
      (c) =>
        c.label.toLowerCase().includes(q) ||
        c.messages.some((m) => m.content.toLowerCase().includes(q))
    );
  }, [conversations, searchQuery]);

  // Filter records by search query
  const filteredRecords = React.useMemo(() => {
    if (!searchQuery.trim()) return records;
    const q = searchQuery.toLowerCase();
    return records.filter(
      (r) =>
        r.content.toLowerCase().includes(q) ||
        r.entities.some((e) => e.toLowerCase().includes(q))
    );
  }, [records, searchQuery]);

  const handleDeleteConversation = (threadId: string) => {
    clearThread(threadId);
    loadConversations();
  };

  const handleClearAllConversations = () => {
    const ok = window.confirm("Are you sure you want to clear all stored conversations from memory?");
    if (ok) {
      clearAllConversations();
      loadConversations();
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveMemory(id);
      await fetchRecords();
    } catch {}
  };

  const handleReject = async (id: string) => {
    try {
      await rejectMemory(id);
      await fetchRecords();
    } catch {}
  };

  const handleForget = async (id: string) => {
    try {
      await forgetMemory(id);
      await fetchRecords();
    } catch {}
  };

  return (
    <div className="flex flex-col w-full gap-5 pb-8 animate-in fade-in-50 duration-200">
      {/* ─── Header Card ─── */}
      <div className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl p-5 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-primary/15 text-primary border border-primary/25 shrink-0">
              <Brain className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-foreground">Sovereign Memory Vault</h1>
                <Badge variant="outline" className="border-primary/40 text-primary text-xs font-mono">
                  Individual Conversations
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Interactions with AI are saved as individual conversations, preserving recall and context across sessions.
              </p>
            </div>
          </div>

          {/* Primary View Toggle: Conversations vs Knowledge Facts */}
          <div className="flex items-center gap-1.5 bg-muted/40 p-1 rounded-xl border border-border/50">
            <button
              type="button"
              onClick={() => setMainTab("conversations")}
              className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all ${
                mainTab === "conversations"
                  ? "bg-primary text-primary-foreground shadow-xs font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5 inline mr-1.5" />
              Conversations ({conversations.length})
            </button>
            <button
              type="button"
              onClick={() => setMainTab("records")}
              className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all ${
                mainTab === "records"
                  ? "bg-primary text-primary-foreground shadow-xs font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Sparkles className="h-3.5 w-3.5 inline mr-1.5" />
              Facts & Policies ({records.length})
            </button>
          </div>
        </div>

        {/* Search & Actions Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-border/50">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder={mainTab === "conversations" ? "Search conversations..." : "Search memory records..."}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-8.5 text-xs bg-muted/20"
            />
          </div>

          {mainTab === "conversations" ? (
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={loadConversations}
                className="h-8 text-xs gap-1.5 text-muted-foreground hover:text-foreground"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Refresh
              </Button>
              {conversations.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleClearAllConversations}
                  className="h-8 text-xs text-muted-foreground hover:text-destructive gap-1"
                >
                  <Trash2 className="h-3.5 w-3.5" /> Clear All
                </Button>
              )}
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={fetchRecords}
              disabled={loading}
              className="h-8 text-xs gap-1.5"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </Button>
          )}
        </div>
      </div>

      {/* ─── MAIN TAB 1: INDIVIDUAL CONVERSATIONS ─── */}
      {mainTab === "conversations" && (
        <div className="space-y-4">
          {/* Direct Interactive AI Interaction in Memory */}
          <Card className="rounded-2xl border border-primary/30 bg-primary/5 p-4 shadow-md">
            <div className="flex items-center gap-2 mb-2 text-xs font-bold text-primary">
              <Sparkles className="h-4 w-4" />
              <span>Interact with Sovereign AI from Memory</span>
            </div>
            <p className="text-[11px] text-muted-foreground mb-3">
              Ask questions or add instructions directly. Every interaction is saved as an individual conversation in memory.
            </p>
            <div className="flex items-center gap-2">
              <Input
                placeholder="Ask sovereign AI to recall, synthesize, or discuss any topic..."
                value={directPrompt}
                onChange={(e) => setDirectPrompt(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleDirectAiSend()}
                disabled={isAiStreaming}
                className="h-9 text-xs bg-background/80"
              />
              <Button
                size="sm"
                onClick={handleDirectAiSend}
                disabled={!directPrompt.trim() || isAiStreaming}
                className="h-9 px-4 gap-1.5 text-xs font-semibold shrink-0"
              >
                {isAiStreaming ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                <span>Send</span>
              </Button>
            </div>

            {/* Live streaming bubble if active */}
            {(isAiStreaming || directStreamText) && (
              <div className="mt-3 p-3.5 rounded-xl bg-card border border-border text-xs space-y-2 animate-in fade-in-50">
                {directThinking && (
                  <div className="text-[11px] text-primary flex items-center gap-1.5 animate-pulse">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    {directThinking}
                  </div>
                )}
                {directStreamText && (
                  <div className="whitespace-pre-wrap text-foreground leading-relaxed">
                    {directStreamText}
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Conversations List */}
          {filteredConversations.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground bg-white/40 dark:bg-black/20 rounded-2xl border border-dashed border-border p-6">
              <MessageSquare className="h-10 w-10 mb-3 opacity-30 text-primary" />
              <h3 className="font-bold text-sm text-foreground">No conversations stored yet</h3>
              <p className="text-xs text-muted-foreground mt-1 max-w-md">
                Interact with the AI using the prompt above, or start a conversation in the Main Chat, Datasets, or Notes tabs. Every session will appear here as an individual conversation.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredConversations.map((thread) => (
                <ConversationCard
                  key={thread.threadId}
                  thread={thread}
                  onDelete={handleDeleteConversation}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── MAIN TAB 2: EXTRACTED MEMORY RECORDS ─── */}
      {mainTab === "records" && (
        <div className="space-y-4">
          {/* Status and Type filter pills */}
          <div className="flex flex-wrap items-center gap-2">
            {(["all", "active", "pending"] as StatusTab[]).map((tab) => (
              <Button
                key={tab}
                size="sm"
                variant={statusTab === tab ? "default" : "outline"}
                className="h-7 text-xs capitalize"
                onClick={() => setStatusTab(tab)}
              >
                {tab}
              </Button>
            ))}

            <div className="w-px h-5 bg-border mx-1" />

            {(["all", "semantic", "episodic", "procedural", "preference"] as TypeFilter[]).map((t) => {
              const Icon = t === "all" ? BookOpen : TYPE_ICONS[t] ?? Brain;
              return (
                <Button
                  key={t}
                  size="sm"
                  variant={typeFilter === t ? "secondary" : "ghost"}
                  className="h-7 text-xs capitalize gap-1"
                  onClick={() => setTypeFilter(t)}
                >
                  <Icon className="h-3 w-3" />
                  {t}
                </Button>
              );
            })}
          </div>

          {/* Records list */}
          {loading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground gap-2">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span>Loading memories...</span>
            </div>
          ) : filteredRecords.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-center">
              <Brain className="h-10 w-10 mb-3 opacity-30 text-primary" />
              <p className="text-sm font-medium">
                {searchQuery
                  ? "No memories match your search."
                  : "No memory records found."}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredRecords.map((rec) => (
                <MemoryCard
                  key={rec.id}
                  memory={rec}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onForget={handleForget}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}