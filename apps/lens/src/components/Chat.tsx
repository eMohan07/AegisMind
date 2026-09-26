import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { streamChat, listModels, type Citation, type ModelInfo } from "@/lib/api";
import {
  Send,
  Square,
  Shield,
  Bot,
  User,
  ExternalLink,
  Sparkles,
  FileText,
  Lock,
  Cpu,
} from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  citations?: Citation[];
  timestamp: string;
}

interface ChatProps {
  currentTenantId: string;
  currentUserId: string;
  initialQuery?: string;
  onClearInitialQuery?: () => void;
}

export function Chat({
  currentTenantId,
  currentUserId,
  initialQuery,
  onClearInitialQuery,
}: ChatProps) {
  const [messages, setMessages] = React.useState<Message[]>([
    {
      id: "msg-welcome",
      role: "assistant",
      content:
        "Welcome to AegisMind. Ask any question across your enterprise repositories. All answers are strictly governed by Zanzibar access control evaluated at retrieval time.",
      timestamp: "Just now",
    },
  ]);
  const [inputQuery, setInputQuery] = React.useState("");
  const [modelInfo, setModelInfo] = React.useState<ModelInfo | null>(null);
  const [selectedModel, setSelectedModel] = React.useState<string>("");
  const [isStreaming, setIsStreaming] = React.useState(false);
  const [currentThinking, setCurrentThinking] = React.useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = React.useState<Citation | null>(null);
  const abortStreamRef = React.useRef<(() => void) | null>(null);
  const messagesEndRef = React.useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  React.useEffect(() => {
    scrollToBottom();
  }, [messages, currentThinking]);

  React.useEffect(() => {
    listModels()
      .then((info) => {
        setModelInfo(info);
        if (info.active_model) {
          setSelectedModel(info.active_model);
        }
      })
      .catch(() => {});
  }, []);

  React.useEffect(() => {
    if (initialQuery) {
      setInputQuery(initialQuery);
      onClearInitialQuery?.();
    }
  }, [initialQuery, onClearInitialQuery]);

  const handleSend = () => {
    if (!inputQuery.trim() || isStreaming) return;

    const userMsgId = `user-${Date.now()}`;
    const assistantMsgId = `asst-${Date.now()}`;
    const query = inputQuery.trim();

    const newMessages: Message[] = [
      ...messages,
      {
        id: userMsgId,
        role: "user",
        content: query,
        timestamp: "Now",
      },
      {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        citations: [],
        timestamp: "Now",
      },
    ];

    setMessages(newMessages);
    setInputQuery("");
    setIsStreaming(true);
    setCurrentThinking("Initializing request...");

    const cancel = streamChat({
      query,
      tenant_id: currentTenantId,
      user_id: currentUserId,
      model: selectedModel || undefined,
      onThinking: (status) => {
        setCurrentThinking(status);
      },
      onToken: (token) => {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, content: msg.content + token }
              : msg
          )
        );
      },
      onCitations: (citations) => {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId ? { ...msg, citations } : msg
          )
        );
      },
      onDone: () => {
        setIsStreaming(false);
        setCurrentThinking(null);
        abortStreamRef.current = null;
      },
      onError: (err) => {
        setIsStreaming(false);
        setCurrentThinking(null);
        abortStreamRef.current = null;
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? {
                  ...msg,
                  content:
                    msg.content ||
                    `Error executing access-controlled search: ${err.message}`,
                }
              : msg
          )
        );
      },
    });

    abortStreamRef.current = cancel;
  };

  const handleStop = () => {
    if (abortStreamRef.current) {
      abortStreamRef.current();
      abortStreamRef.current = null;
    }
    setIsStreaming(false);
    setCurrentThinking(null);
  };

  return (
    <div className="flex h-full flex-col lg:flex-row gap-4 p-4 max-w-7xl mx-auto w-full">
      {/* Main Conversation Column */}
      <div className="flex flex-1 flex-col h-[calc(100vh-8rem)] rounded-xl border border-border/80 bg-card/40 backdrop-blur-sm overflow-hidden">
        {/* Context Header */}
        <div className="flex items-center justify-between border-b border-border/70 px-4 py-3 bg-muted/20">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-emerald-400" />
            <span className="text-xs font-medium text-foreground">
              Zanzibar Enforced Session
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">Tenant:</span>
            <Badge variant="outline" className="font-mono text-[11px]">
              {currentTenantId}
            </Badge>
            <span className="text-muted-foreground ml-2">User:</span>
            <Badge variant="outline" className="font-mono text-[11px] text-primary">
              {currentUserId}
            </Badge>
            <div className="flex items-center gap-1.5 ml-2 border-l border-border/60 pl-2">
              <Cpu className="h-3.5 w-3.5 text-primary" />
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="bg-transparent text-xs font-mono text-foreground focus:outline-none cursor-pointer"
                title="Select Ollama model"
              >
                {modelInfo?.models && modelInfo.models.length > 0 ? (
                  modelInfo.models.map((m) => (
                    <option key={m} value={m} className="bg-card">
                      {m}
                    </option>
                  ))
                ) : (
                  <option value="llama3.2:latest" className="bg-card">
                    llama3.2:latest
                  </option>
                )}
              </select>
            </div>
          </div>
        </div>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${
                msg.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              {msg.role === "assistant" && (
                <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-lg bg-primary/20 text-primary border border-primary/30">
                  <Bot className="h-4 w-4" />
                </div>
              )}

              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted/50 border border-border/60 text-foreground"
                }`}
              >
                {/* Message Body */}
                <div className="whitespace-pre-wrap leading-relaxed">
                  {msg.content}
                </div>

                {/* Interactive Citations list */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-border/40">
                    <div className="text-[11px] font-semibold text-muted-foreground mb-1.5 flex items-center gap-1">
                      <Sparkles className="h-3 w-3 text-amber-400" />
                      Verified Source Citations:
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.citations.map((cit, idx) => (
                        <button
                          key={cit.chunk_id}
                          type="button"
                          onClick={() => setSelectedCitation(cit)}
                          className="inline-flex items-center gap-1 rounded-md border border-border/60 bg-background/80 px-2 py-0.5 text-xs text-foreground hover:border-primary hover:text-primary transition-all shadow-xs"
                        >
                          <span className="font-mono font-bold text-[10px] text-primary">
                            [{idx + 1}]
                          </span>
                          <span className="truncate max-w-[150px]">{cit.title}</span>
                          <Badge variant="success" className="text-[9px] px-1 py-0 ml-0.5">
                            {Math.round(cit.score * 100)}%
                          </Badge>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div
                  className={`mt-1 text-[10px] ${
                    msg.role === "user"
                      ? "text-primary-foreground/70 text-right"
                      : "text-muted-foreground text-left"
                  }`}
                >
                  {msg.timestamp}
                </div>
              </div>

              {msg.role === "user" && (
                <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-lg bg-muted text-muted-foreground border border-border/60">
                  <User className="h-4 w-4" />
                </div>
              )}
            </div>
          ))}

          {/* Thinking Status Indicator */}
          {currentThinking && (
            <div className="flex gap-3 items-center text-xs text-muted-foreground animate-pulse pl-11">
              <Lock className="h-3.5 w-3.5 text-emerald-400" />
              <span>{currentThinking}</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="border-t border-border/70 p-3 bg-card/60">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex gap-2"
          >
            <Input
              placeholder="Ask anything (e.g. How does zero stale read revocation work?)..."
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              disabled={isStreaming}
              className="flex-1 bg-background/90"
            />
            {isStreaming ? (
              <Button
                type="button"
                variant="destructive"
                onClick={handleStop}
                className="gap-1.5"
              >
                <Square className="h-4 w-4 fill-current" />
                Stop
              </Button>
            ) : (
              <Button
                type="submit"
                disabled={!inputQuery.trim()}
                className="gap-1.5"
              >
                <Send className="h-4 w-4" />
                Send
              </Button>
            )}
          </form>
        </div>
      </div>

      {/* Interactive Citation Detail Panel */}
      {selectedCitation ? (
        <div className="w-full lg:w-96 rounded-xl border border-border/80 bg-card/50 p-4 backdrop-blur-sm flex flex-col justify-between animate-in slide-in-from-right-4 duration-200">
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b border-border/50 pb-2">
              <div className="flex items-center gap-1.5">
                <FileText className="h-4 w-4 text-primary" />
                <span className="text-xs font-semibold text-foreground">
                  Citation Inspector
                </span>
              </div>
              <button
                type="button"
                onClick={() => setSelectedCitation(null)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Close
              </button>
            </div>

            <div>
              <h4 className="text-sm font-semibold text-foreground leading-tight">
                {selectedCitation.title}
              </h4>
              <p className="text-xs text-muted-foreground font-mono mt-0.5">
                ID: {selectedCitation.document_id}
              </p>
            </div>

            <Card className="bg-background/60 border-border/60">
              <CardContent className="p-3 text-xs text-muted-foreground leading-relaxed">
                <span className="font-semibold text-foreground">Extracted Snippet:</span>
                <p className="mt-1 italic">"{selectedCitation.snippet}"</p>
              </CardContent>
            </Card>

            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Reranker Relevance:</span>
              <Badge variant="success">
                {(selectedCitation.score * 100).toFixed(1)}% match
              </Badge>
            </div>

            <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-2.5 text-xs text-emerald-400 flex items-center gap-2">
              <Shield className="h-4 w-4 shrink-0" />
              <span>Zanzibar policy check passed for user {currentUserId}</span>
            </div>
          </div>

          <div className="pt-4 border-t border-border/50">
            <Button
              variant="outline"
              size="sm"
              className="w-full gap-1.5 text-xs"
              onClick={() => window.open(selectedCitation.uri, "_blank")}
            >
              Open Resource
              <ExternalLink className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      ) : (
        <div className="hidden lg:flex w-80 rounded-xl border border-dashed border-border/60 p-6 flex-col items-center justify-center text-center text-muted-foreground">
          <FileText className="h-8 w-8 mb-2 opacity-40" />
          <p className="text-xs font-medium">Citation Preview</p>
          <p className="text-[11px] text-muted-foreground/80 mt-1">
            Click any verified citation badge in the answer to view its source snippet and security token status.
          </p>
        </div>
      )}
    </div>
  );
}
