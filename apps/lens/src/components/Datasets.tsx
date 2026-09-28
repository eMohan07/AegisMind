import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import {
  chatWithDataset,
  ingestDocument,
  deleteDocument,
  listIndexedResources,
  listModels,
  uploadDocumentFile,
  type ModelInfo,
  type ResourceItem,
} from "@/lib/api";
import { recordExchange } from "@/lib/conversationStore";
import {
  Database,
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertCircle,
  Trash2,
  Cpu,
  Lock,
  RefreshCw,
  Search,
  MessageSquare,
  Users,
  Send,
  Copy,
  Check,
  Maximize2,
  Minimize2,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Sparkles,
} from "lucide-react";
import { format12HrDateTime } from "@/lib/utils";

interface DatasetsProps {
  currentTenantId: string;
  currentUserId: string;
  onNavigateToChat?: (query?: string) => void;
}

interface DatasetChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  memorySaved?: boolean;
}

type ChatHeightPreset = "compact" | "standard" | "enlarged";

export function Datasets({
  currentTenantId,
  currentUserId,
  onNavigateToChat,
}: DatasetsProps) {
  // Datasets & Resources State
  const [resources, setResources] = React.useState<ResourceItem[]>([]);
  const [activeDatasetId, setActiveDatasetId] = React.useState<string | null>(() => {
    try {
      return localStorage.getItem("aegismind_active_dataset_id");
    } catch {
      return null;
    }
  });
  const [searchFilter, setSearchFilter] = React.useState("");
  const [isLoadingResources, setIsLoadingResources] = React.useState(false);
  const [isDeleting, setIsDeleting] = React.useState<string | null>(null);

  // Model State
  const [modelInfo, setModelInfo] = React.useState<ModelInfo | null>(null);
  const [selectedModel, setSelectedModel] = React.useState<string>("");

  // Ingest State
  const [showManualForm, setShowManualForm] = React.useState(false);
  const [isIngestingFile, setIsIngestingFile] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [content, setContent] = React.useState("");
  const [documentId, setDocumentId] = React.useState("");
  const [allowedUsers, setAllowedUsers] = React.useState<string[]>([currentUserId]);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  // Individual Dataset Chat State
  const [datasetConversations, setDatasetConversations] = React.useState<
    Record<string, DatasetChatMessage[]>
  >(() => {
    try {
      const saved = localStorage.getItem("aegismind_dataset_conversations");
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });
  const [chatQuery, setChatQuery] = React.useState("");
  const [isChatting, setIsChatting] = React.useState(false);
  const [copiedId, setCopiedId] = React.useState<string | null>(null);
  const [memorySyncNotice, setMemorySyncNotice] = React.useState<string | null>(null);

  // Layout & Crop Controls
  const [isSidebarCropped, setIsSidebarCropped] = React.useState(false);
  const [chatHeightPreset, setChatHeightPreset] = React.useState<ChatHeightPreset>("standard");

  // Notifications
  const [feedback, setFeedback] = React.useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const quickFileInputRef = React.useRef<HTMLInputElement>(null);
  const messagesEndRef = React.useRef<HTMLDivElement>(null);

  const availablePrincipals = [
    { id: "alice", label: "alice (eng)" },
    { id: "bob", label: "bob (contractor)" },
    { id: "charlie", label: "charlie (finance)" },
    { id: "*", label: "* (all tenant members)" },
  ];

  // Sync active dataset ID to localStorage
  React.useEffect(() => {
    if (activeDatasetId) {
      try {
        localStorage.setItem("aegismind_active_dataset_id", activeDatasetId);
      } catch {
        // Ignored
      }
    }
  }, [activeDatasetId]);

  // Sync dataset conversations to localStorage
  React.useEffect(() => {
    try {
      localStorage.setItem(
        "aegismind_dataset_conversations",
        JSON.stringify(datasetConversations)
      );
    } catch {
      // Ignored
    }
  }, [datasetConversations]);

  // Auto-scroll chat messages to bottom
  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeDatasetId, datasetConversations, isChatting]);

  // Load resources and models
  const fetchResourcesAndModels = React.useCallback(async () => {
    setIsLoadingResources(true);
    try {
      const [models, resList] = await Promise.all([
        listModels(),
        listIndexedResources(),
      ]);
      setModelInfo(models);
      if (!selectedModel && models.active_model) {
        setSelectedModel(models.active_model);
      }
      setResources(resList);

      // Auto-select first resource if none currently selected
      setActiveDatasetId((prev) => {
        if (prev && resList.some((r) => r.id === prev)) {
          return prev;
        }
        return resList.length > 0 ? resList[0]!.id : null;
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load datasets";
      setFeedback({ type: "error", message: msg });
    } finally {
      setIsLoadingResources(false);
    }
  }, [selectedModel]);

  React.useEffect(() => {
    fetchResourcesAndModels();
  }, [fetchResourcesAndModels]);

  // Active dataset object
  const activeDataset = React.useMemo(() => {
    return resources.find((r) => r.id === activeDatasetId) || null;
  }, [resources, activeDatasetId]);

  // Active dataset conversation messages
  const activeMessages = React.useMemo(() => {
    if (!activeDatasetId) return [];
    return datasetConversations[activeDatasetId] || [];
  }, [activeDatasetId, datasetConversations]);

  const togglePrincipal = (principalId: string) => {
    setAllowedUsers((prev) => {
      if (prev.includes(principalId)) {
        return prev.filter((p) => p !== principalId);
      }
      return [...prev, principalId];
    });
  };

  // Instant 1-Click Ingest for any file type (PDF, PPT, DOCX, TXT, CSV, JSON, etc.)
  const handleDirectFileIngest = async (file: File) => {
    setIsIngestingFile(true);
    setFeedback(null);

    const cleanName = file.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " ");
    const formattedTitle = cleanName.charAt(0).toUpperCase() + cleanName.slice(1);

    try {
      const effectiveAllowed =
        allowedUsers.length > 0 ? allowedUsers : [currentUserId, "alice", "bob"];

      const res = await uploadDocumentFile(file, {
        title: formattedTitle,
        tenant_id: currentTenantId,
        allowed_users: effectiveAllowed,
      });

      const newResource: ResourceItem = {
        id: res.document_id,
        title: res.title,
        type: res.file_type || "document",
        connector: "file_upload",
        chunk_count: res.chunk_count || res.chunks_count || 1,
        chunks_count: res.chunk_count || res.chunks_count || 1,
        content: res.content || "",
        file_type: res.file_type,
        page_count: res.page_count,
        char_count: res.char_count,
        allowed_users: res.allowed_users,
      };

      setResources((prev) => [newResource, ...prev.filter((r) => r.id !== newResource.id)]);
      setActiveDatasetId(res.document_id);

      setFeedback({
        type: "success",
        message: `Successfully ingested "${res.title}" with ${res.chunk_count || 1} chunks into database. Dedicated chatbox ready!`,
      });

      await fetchResourcesAndModels();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "File ingestion failed";
      setFeedback({
        type: "error",
        message: `Direct ingest failed for ${file.name}: ${msg}`,
      });
    } finally {
      setIsIngestingFile(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (quickFileInputRef.current) quickFileInputRef.current.value = "";
    }
  };

  // Manual Form Ingestion
  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !content.trim()) {
      setFeedback({
        type: "error",
        message: "Please provide both a dataset title and content.",
      });
      return;
    }

    setIsSubmitting(true);
    setFeedback(null);

    try {
      const effectiveAllowed =
        allowedUsers.length > 0 ? allowedUsers : [currentUserId];
      const res = await ingestDocument({
        title: title.trim(),
        content: content.trim(),
        document_id: documentId.trim() || undefined,
        tenant_id: currentTenantId,
        allowed_users: effectiveAllowed,
      });

      const newResource: ResourceItem = {
        id: res.document_id,
        title: res.title,
        type: "custom_dataset",
        connector: "dataset_ingest",
        chunk_count: res.chunk_count || res.chunks_count || 1,
        chunks_count: res.chunk_count || res.chunks_count || 1,
        content: content.trim(),
        allowed_users: res.allowed_users,
      };

      setResources((prev) => [newResource, ...prev.filter((r) => r.id !== newResource.id)]);
      setActiveDatasetId(res.document_id);

      setFeedback({
        type: "success",
        message: `Successfully indexed "${res.title}" with ${res.chunk_count || 1} vector chunks. Sovereign access granted to: ${res.allowed_users.join(", ")}.`,
      });

      setTitle("");
      setContent("");
      setDocumentId("");
      setShowManualForm(false);

      await fetchResourcesAndModels();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to ingest dataset";
      setFeedback({
        type: "error",
        message: `Ingestion failed: ${msg}`,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Delete Dataset with Access Revocation
  const handleDelete = async (docId: string, docTitle: string) => {
    if (!confirm(`Are you sure you want to delete and revoke "${docTitle}"?`)) {
      return;
    }

    setIsDeleting(docId);
    try {
      await deleteDocument(docId);
      setFeedback({
        type: "success",
        message: `Dataset "${docTitle}" deleted and sovereign access revoked.`,
      });

      setResources((prev) => prev.filter((r) => r.id !== docId));
      if (activeDatasetId === docId) {
        const remaining = resources.filter((r) => r.id !== docId);
        setActiveDatasetId(remaining.length > 0 ? remaining[0]!.id : null);
      }

      await fetchResourcesAndModels();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete dataset";
      setFeedback({
        type: "error",
        message: `Deletion failed: ${msg}`,
      });
    } finally {
      setIsDeleting(null);
    }
  };

  // Execute Question in Active Dataset's Dedicated Chatbox
  const handleDatasetQuery = async (queryText?: string) => {
    const textToSend = (queryText ?? chatQuery).trim();
    if (!textToSend || !activeDataset || isChatting) return;

    const currentDocId = activeDataset.id;
    const userMsg: DatasetChatMessage = {
      id: `usr-${Date.now()}`,
      role: "user",
      content: textToSend,
      timestamp: "Just now",
    };

    setDatasetConversations((prev) => ({
      ...prev,
      [currentDocId]: [...(prev[currentDocId] || []), userMsg],
    }));

    setChatQuery("");
    setIsChatting(true);

    try {
      const res = await chatWithDataset({
        document_id: activeDataset.id,
        title: activeDataset.title,
        content: activeDataset.content,
        query: textToSend,
        user_id: currentUserId,
        tenant_id: currentTenantId,
      });

      const assistantMsg: DatasetChatMessage = {
        id: `asst-${Date.now()}`,
        role: "assistant",
        content: res.answer,
        timestamp: new Date().toISOString(),
        memorySaved: true,
      };

      setDatasetConversations((prev) => ({
        ...prev,
        [currentDocId]: [...(prev[currentDocId] || []), assistantMsg],
      }));

      // Persist to cross-chatbox conversation store for Memory aggregation
      recordExchange({
        threadId: `dataset-${currentDocId}`,
        label: `Dataset: ${activeDataset.title}`,
        source: "dataset",
        userMessage: {
          id: userMsg.id,
          content: textToSend,
          timestamp: new Date().toISOString(),
        },
        assistantMessage: {
          id: assistantMsg.id,
          content: res.answer,
          timestamp: new Date().toISOString(),
        },
      });

      setMemorySyncNotice("Preserved in Long-Term Memory");
      setTimeout(() => setMemorySyncNotice(null), 3500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Query execution failed";
      setDatasetConversations((prev) => ({
        ...prev,
        [currentDocId]: [
          ...(prev[currentDocId] || []),
          {
            id: `err-${Date.now()}`,
            role: "assistant",
            content: `Dataset query error: ${msg}. Please ensure Ollama is running and try again.`,
            timestamp: "Just now",
          },
        ],
      }));
    } finally {
      setIsChatting(false);
    }
  };

  // Clear Chat History for Active Dataset
  const handleClearCurrentChat = () => {
    if (!activeDatasetId) return;
    setDatasetConversations((prev) => {
      const copy = { ...prev };
      delete copy[activeDatasetId];
      return copy;
    });
  };

  const copyMessageContent = async (msgId: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(msgId);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // Ignored
    }
  };

  const filteredResources = resources.filter((res) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return (
      res.title.toLowerCase().includes(q) ||
      res.id.toLowerCase().includes(q) ||
      (res.connector && res.connector.toLowerCase().includes(q))
    );
  });

  const getChatHeightClass = () => {
    switch (chatHeightPreset) {
      case "compact":
        return "h-[360px]";
      case "enlarged":
        return "h-[620px]";
      case "standard":
      default:
        return "h-[490px]";
    }
  };

  return (
    <div className="p-4 max-w-7xl mx-auto w-full space-y-5">
      {/* Top Banner: Ollama LLM Engine & Quick 1-Click File Ingest */}
      <Card className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-xl">
        <CardContent className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-primary/10 border border-primary/30 flex items-center justify-center text-primary shrink-0">
              <Database className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground">
                  AegisMind Database & Knowledge Corpus
                </h3>
                <Badge
                  variant="outline"
                  className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[10px] font-mono"
                >
                  <Cpu className="h-3 w-3 mr-1" />
                  Ollama Active
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground">
                Ingest any dataset or file (PDF, DOC, PPT, TXT, CSV, JSON). Each file receives an individual chatbox grounded strictly on its records.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Quick 1-Click Upload & Ingest Button */}
            <Button
              type="button"
              variant="default"
              size="sm"
              disabled={isIngestingFile}
              onClick={() => quickFileInputRef.current?.click()}
              className="h-8 gap-1.5 text-xs bg-primary hover:bg-primary/90 text-primary-foreground font-medium shadow-sm"
              title="Upload and immediately index any file into the database"
            >
              {isIngestingFile ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  <span>Ingesting File...</span>
                </>
              ) : (
                <>
                  <UploadCloud className="h-3.5 w-3.5" />
                  <span>Upload & Ingest File</span>
                </>
              )}
            </Button>
            <input
              ref={quickFileInputRef}
              type="file"
              accept="*/*"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleDirectFileIngest(file);
              }}
              className="hidden"
            />

            {/* Manual Form Toggle */}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowManualForm((prev) => !prev)}
              className="h-8 text-xs gap-1.5"
              title="Toggle manual text paste and sovereign access configuration"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>{showManualForm ? "Hide Form" : "Custom Text Ingest"}</span>
            </Button>

            {/* Model Selector */}
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="bg-secondary text-xs font-mono px-2.5 py-1.5 rounded-md border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer h-8"
              title="Active Ollama model"
            >
              {modelInfo?.models && modelInfo.models.length > 0 ? (
                modelInfo.models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))
              ) : (
                <option value="llama3.2:latest">llama3.2:latest</option>
              )}
            </select>

            {/* Refresh */}
            <Button
              variant="outline"
              size="sm"
              onClick={fetchResourcesAndModels}
              className="h-8 w-8 p-0"
              title="Refresh models and datasets"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${isLoadingResources ? "animate-spin" : ""}`}
              />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Feedback Banner */}
      {feedback && (
        <div
          className={`p-3 rounded-lg text-xs flex items-center gap-2 border transition-all ${
            feedback.type === "success"
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
              : "bg-destructive/10 text-destructive border-destructive/30"
          }`}
        >
          {feedback.type === "success" ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 shrink-0" />
          )}
          <span className="flex-1">{feedback.message}</span>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            className="text-muted-foreground hover:text-foreground text-xs px-1"
          >
            ✕
          </button>
        </div>
      )}

      {/* Collapsible Manual Ingest Form */}
      {showManualForm && (
        <Card className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-xl animate-in fade-in-50 duration-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Database className="h-4 w-4 text-primary" />
              Manual Text & Sovereign Access Policy Ingestion
            </CardTitle>
            <CardDescription className="text-xs">
              Directly paste structured text, records, or specifications. AegisMind segments, generates embeddings, and configures sovereign access policies.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleManualSubmit} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-foreground">
                    Dataset Title <span className="text-primary">*</span>
                  </label>
                  <Input
                    placeholder="e.g. Q4 Financial Ledger or Security Policy"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    required
                    className="h-8 text-xs bg-muted/30"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground flex items-center justify-between">
                    <span>Document ID (optional)</span>
                    <span className="font-mono text-[10px]">Auto-generated if blank</span>
                  </label>
                  <Input
                    placeholder="e.g. doc-sec-892"
                    value={documentId}
                    onChange={(e) => setDocumentId(e.target.value)}
                    className="h-8 text-xs font-mono bg-muted/30"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-foreground">
                    Dataset Content / Records <span className="text-primary">*</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isIngestingFile}
                    className="text-[11px] text-primary hover:underline flex items-center gap-1 font-medium"
                  >
                    <UploadCloud className="h-3 w-3" />
                    <span>Or Select File to Ingest Directly</span>
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="*/*"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleDirectFileIngest(file);
                    }}
                    className="hidden"
                  />
                </div>
                <textarea
                  rows={5}
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="Paste dataset records, markdown documents, code, or logs..."
                  required
                  className="w-full rounded-md border border-input bg-muted/30 px-3 py-2 text-xs font-mono placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                />
              </div>

              {/* Sovereign Access Policy */}
              <div className="space-y-2 border-t border-border/60 pt-3">
                <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                  <Lock className="h-3.5 w-3.5 text-emerald-400" />
                  <span>Sovereign Access Authorization Policy</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {availablePrincipals.map((p) => {
                    const isChecked = allowedUsers.includes(p.id);
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => togglePrincipal(p.id)}
                        className={`flex items-center gap-2 p-2 rounded-md border text-left text-xs transition-colors ${
                          isChecked
                            ? "bg-primary/10 border-primary/40 text-foreground font-medium"
                            : "border-border/60 text-muted-foreground hover:bg-muted/40"
                        }`}
                      >
                        <div
                          className={`h-3.5 w-3.5 rounded flex items-center justify-center border text-[10px] ${
                            isChecked
                              ? "bg-primary text-primary-foreground border-primary"
                              : "border-muted-foreground"
                          }`}
                        >
                          {isChecked ? "✓" : ""}
                        </div>
                        <span className="font-mono text-[11px] truncate">{p.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowManualForm(false)}
                  className="h-8 text-xs"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={isSubmitting || !title.trim() || !content.trim()}
                  className="h-8 gap-2 text-xs"
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      Chunking & Embedding...
                    </>
                  ) : (
                    <>
                      <UploadCloud className="h-3.5 w-3.5" />
                      Ingest & Index Dataset
                    </>
                  )}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Main Workspace: Datasets Repository (Left) & Dedicated Individual Chatbox (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left Column: Datasets List (Can be cropped/hidden to enlarge chatbox) */}
        {!isSidebarCropped && (
          <div className="lg:col-span-5 space-y-3">
            <Card className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-xl">
              <CardHeader className="p-3.5 pb-2 flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-sm flex items-center gap-2">
                    <FileText className="h-4 w-4 text-emerald-400" />
                    Indexed Datasets ({filteredResources.length})
                  </CardTitle>
                  <CardDescription className="text-[11px]">
                    Select any dataset to launch its individual chatbox.
                  </CardDescription>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsSidebarCropped(true)}
                  className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                  title="Enlarge chatbox (Collapse dataset list)"
                >
                  <PanelLeftClose className="h-4 w-4" />
                </Button>
              </CardHeader>
              <CardContent className="p-3.5 pt-0 space-y-2.5">
                {/* Search & Drag/Drop Trigger */}
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder="Search datasets by title or ID..."
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    className="pl-8 h-8 text-xs bg-muted/30"
                  />
                </div>

                {/* Dropzone notice */}
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const droppedFile = e.dataTransfer.files?.[0];
                    if (droppedFile) handleDirectFileIngest(droppedFile);
                  }}
                  onClick={() => quickFileInputRef.current?.click()}
                  className="p-2.5 border border-dashed border-border/80 hover:border-primary/50 hover:bg-primary/5 rounded-lg text-center cursor-pointer transition-colors"
                >
                  <div className="flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground font-medium">
                    <UploadCloud className="h-3.5 w-3.5 text-primary" />
                    <span>Drop files here or click to ingest into database</span>
                  </div>
                </div>

                {/* Datasets List */}
                <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
                  {isLoadingResources && resources.length === 0 ? (
                    <div className="p-8 text-center text-xs text-muted-foreground">
                      <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-primary" />
                      Loading indexed datasets...
                    </div>
                  ) : filteredResources.length === 0 ? (
                    <div className="p-8 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
                      No datasets found. Drop a file above to immediately ingest it into the database.
                    </div>
                  ) : (
                    filteredResources.map((res) => {
                      const isSelected = res.id === activeDatasetId;
                      return (
                        <div
                          key={res.id}
                          onClick={() => setActiveDatasetId(res.id)}
                          className={`p-3 rounded-lg border transition-all cursor-pointer ${
                            isSelected
                              ? "bg-primary/10 border-primary/60 shadow-sm"
                              : "bg-card/40 border-border/70 hover:bg-card/80 hover:border-border"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="space-y-1 min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="font-semibold text-xs text-foreground truncate">
                                  {res.title}
                                </span>
                                {isSelected && (
                                  <Badge className="bg-primary text-primary-foreground text-[9px] py-0 px-1.5 h-4">
                                    Active Chat
                                  </Badge>
                                )}
                              </div>
                              <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                                <span className="font-mono">{res.id}</span>
                                <span>•</span>
                                <span>{res.chunk_count ?? res.chunks_count ?? 1} chunks</span>
                                {res.file_type && (
                                  <>
                                    <span>•</span>
                                    <span className="uppercase font-mono">{res.file_type}</span>
                                  </>
                                )}
                                {res.allowed_users && res.allowed_users.length > 0 && (
                                  <>
                                    <span>•</span>
                                    <span className="flex items-center gap-0.5 text-emerald-400">
                                      <Users className="h-2.5 w-2.5" />
                                      <span>{res.allowed_users.join(", ")}</span>
                                    </span>
                                  </>
                                )}
                              </div>
                            </div>

                            <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                              <Button
                                variant={isSelected ? "default" : "outline"}
                                size="sm"
                                onClick={() => setActiveDatasetId(res.id)}
                                className="h-6 text-[10px] px-2 gap-1"
                                title="Open individual chatbox for this dataset"
                              >
                                <MessageSquare className="h-2.5 w-2.5" />
                                Chat
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                disabled={isDeleting === res.id}
                                onClick={() => handleDelete(res.id, res.title)}
                                className="h-6 w-6 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                                title="Delete dataset and revoke sovereign authorization"
                              >
                                {isDeleting === res.id ? (
                                  <RefreshCw className="h-3 w-3 animate-spin" />
                                ) : (
                                  <Trash2 className="h-3 w-3" />
                                )}
                              </Button>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Right Column: Dedicated Individual Dataset Chatbox */}
        <div className={isSidebarCropped ? "lg:col-span-12" : "lg:col-span-7"}>
          {activeDataset ? (
            <Card className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-xl flex flex-col">
              {/* Chatbox Header with Dataset Metadata & Crop/Resize Controls */}
              <CardHeader className="p-3.5 pb-2.5 border-b border-border/60">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <MessageSquare className="h-4 w-4 text-primary" />
                        <span>Chat: {activeDataset.title}</span>
                      </CardTitle>
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {activeDataset.id}
                      </Badge>
                      <Badge variant="secondary" className="text-[10px]">
                        {activeDataset.chunk_count ?? activeDataset.chunks_count ?? 1} chunks
                      </Badge>
                      {activeDataset.file_type && (
                        <Badge variant="outline" className="text-[9px] uppercase font-mono border-primary/30 text-primary">
                          {activeDataset.file_type}
                        </Badge>
                      )}
                    </div>
                    <CardDescription className="text-[11px]">
                      Dedicated chatbox grounded specifically on this dataset with verified sovereign access control.
                    </CardDescription>
                  </div>

                  {/* Header Actions: Long-Term Memory Badge, Crop, Height Preset, Clear */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    {/* Long-term memory notification */}
                    {memorySyncNotice ? (
                      <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 text-[10px] animate-pulse">
                        <Sparkles className="h-3 w-3 mr-1" />
                        {memorySyncNotice}
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] text-muted-foreground border-border/80 font-mono">
                        Memory Synced
                      </Badge>
                    )}

                    {/* Size toggle (Enlarge / Restore chatbox) */}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setIsSidebarCropped((prev) => !prev)}
                      className="h-7 w-7 p-0"
                      title={isSidebarCropped ? "Show dataset list (Restore chatbox)" : "Enlarge chatbox (Collapse dataset list)"}
                    >
                      {isSidebarCropped ? (
                        <PanelLeftOpen className="h-3.5 w-3.5" />
                      ) : (
                        <PanelLeftClose className="h-3.5 w-3.5" />
                      )}
                    </Button>

                    {/* Height Preset Toggle */}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        setChatHeightPreset((prev) =>
                          prev === "compact"
                            ? "standard"
                            : prev === "standard"
                            ? "enlarged"
                            : "compact"
                        )
                      }
                      className="h-7 w-7 p-0"
                      title={`Resize chatbox height (currently: ${chatHeightPreset})`}
                    >
                      {chatHeightPreset === "enlarged" ? (
                        <Minimize2 className="h-3 w-3" />
                      ) : (
                        <Maximize2 className="h-3 w-3" />
                      )}
                    </Button>

                    {/* Clear Chat */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleClearCurrentChat}
                      disabled={activeMessages.length === 0}
                      className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive"
                      title="Clear chat history for this dataset"
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              </CardHeader>

              {/* Chat Messages Container */}
              <div
                className={`p-3.5 overflow-y-auto space-y-3.5 bg-background/30 transition-all ${getChatHeightClass()}`}
              >
                {/* Initial Dataset Assistant Welcome Message */}
                <div className="flex gap-2.5 text-xs">
                  <div className="h-7 w-7 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center text-primary shrink-0 mt-0.5">
                    <Sparkles className="h-3.5 w-3.5" />
                  </div>
                  <div className="space-y-1 max-w-[88%]">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground text-xs">
                        Dataset Assistant
                      </span>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        {selectedModel || "llama3.2:latest"}
                      </span>
                    </div>
                    <div className="p-3 rounded-lg bg-card/70 border border-border/80 text-foreground space-y-1.5 leading-relaxed text-xs">
                      <p>
                        Welcome! This individual chatbox is strictly dedicated to answering questions with respect to{" "}
                        <span className="font-semibold text-primary">{activeDataset.title}</span>.
                      </p>
                      <p className="text-muted-foreground text-[11px]">
                        Responses are generated using local Ollama grounded directly on this dataset&apos;s records. All questions and answers are stored in AegisMind long-term memory.
                      </p>
                    </div>
                  </div>
                </div>

                {/* User and Assistant Messages */}
                {activeMessages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex gap-2.5 text-xs ${
                      msg.role === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    {msg.role === "assistant" && (
                      <div className="h-7 w-7 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center text-primary shrink-0 mt-0.5">
                        <Cpu className="h-3.5 w-3.5" />
                      </div>
                    )}

                    <div
                      className={`space-y-1 max-w-[85%] ${
                        msg.role === "user" ? "items-end text-right" : "items-start text-left"
                      }`}
                    >
                      <div
                        className={`flex items-center gap-2 text-[10px] text-muted-foreground ${
                          msg.role === "user" ? "justify-end" : "justify-start"
                        }`}
                      >
                        <span className="font-medium text-foreground">
                          {msg.role === "user" ? "You" : "Dataset Assistant"}
                        </span>
                        <span>{format12HrDateTime(msg.timestamp)}</span>
                        {msg.memorySaved && (
                          <span className="text-emerald-400 font-mono text-[9px] flex items-center gap-0.5">
                            <Sparkles className="h-2.5 w-2.5" />
                            Memory Saved
                          </span>
                        )}
                      </div>

                      <div
                        className={`p-3 rounded-lg leading-relaxed whitespace-pre-wrap ${
                          msg.role === "user"
                            ? "bg-primary text-primary-foreground font-medium rounded-tr-none text-xs"
                            : "bg-card/75 border border-border/80 text-foreground rounded-tl-none text-xs"
                        }`}
                      >
                        {msg.content}
                      </div>

                      {msg.role === "assistant" && (
                        <div className="flex items-center gap-1.5 pt-0.5">
                          <button
                            type="button"
                            onClick={() => copyMessageContent(msg.id, msg.content)}
                            className="text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-muted/50"
                            title="Copy answer to clipboard"
                          >
                            {copiedId === msg.id ? (
                              <>
                                <Check className="h-3 w-3 text-emerald-400" />
                                <span className="text-emerald-400">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy className="h-3 w-3" />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        </div>
                      )}
                    </div>

                    {msg.role === "user" && (
                      <div className="h-7 w-7 rounded-full bg-secondary border border-border flex items-center justify-center text-foreground shrink-0 mt-0.5 text-xs font-semibold">
                        U
                      </div>
                    )}
                  </div>
                ))}

                {/* Loading / Generating State */}
                {isChatting && (
                  <div className="flex gap-2.5 text-xs">
                    <div className="h-7 w-7 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center text-primary shrink-0 animate-pulse">
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                        <span className="font-semibold text-foreground">Dataset Assistant</span>
                        <span>Grounding on dataset records...</span>
                      </div>
                      <div className="p-3 rounded-lg bg-card/60 border border-border/70 text-muted-foreground flex items-center gap-2 text-xs">
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary animate-bounce" />
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary animate-bounce [animation-delay:0.2s]" />
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary animate-bounce [animation-delay:0.4s]" />
                        <span className="ml-1 text-[11px]">Synthesizing with local Ollama weights...</span>
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Quick Prompt Chips for Active Dataset */}
              <div className="px-3.5 py-2 border-t border-border/50 bg-card/30 flex items-center gap-1.5 overflow-x-auto text-[11px] no-scrollbar">
                <span className="text-[10px] text-muted-foreground shrink-0 flex items-center gap-1">
                  <Sparkles className="h-3 w-3 text-primary" />
                  Quick prompts:
                </span>
                <button
                  type="button"
                  disabled={isChatting}
                  onClick={() => handleDatasetQuery("Summarize the key records and main findings in this dataset.")}
                  className="px-2 py-1 rounded bg-secondary/80 hover:bg-secondary border border-border/60 text-foreground shrink-0 transition-colors"
                >
                  Summarize key records
                </button>
                <button
                  type="button"
                  disabled={isChatting}
                  onClick={() => handleDatasetQuery("Extract all quantitative metrics, statistics, and figures.")}
                  className="px-2 py-1 rounded bg-secondary/80 hover:bg-secondary border border-border/60 text-foreground shrink-0 transition-colors"
                >
                  Extract metrics & figures
                </button>
                <button
                  type="button"
                  disabled={isChatting}
                  onClick={() => handleDatasetQuery("What are the primary operational guidelines established in this content?")}
                  className="px-2 py-1 rounded bg-secondary/80 hover:bg-secondary border border-border/60 text-foreground shrink-0 transition-colors"
                >
                  Operational guidelines
                </button>
                <button
                  type="button"
                  disabled={isChatting}
                  onClick={() => handleDatasetQuery("Verify sovereign authorization and access security for this dataset.")}
                  className="px-2 py-1 rounded bg-secondary/80 hover:bg-secondary border border-border/60 text-foreground shrink-0 transition-colors"
                >
                  Sovereign access check
                </button>
              </div>

              {/* Chat Input Footer */}
              <div className="p-3.5 border-t border-border/60 bg-card/40">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleDatasetQuery();
                  }}
                  className="flex items-center gap-2"
                >
                  <Input
                    value={chatQuery}
                    onChange={(e) => setChatQuery(e.target.value)}
                    placeholder={`Ask any question grounded specifically on ${activeDataset.title}...`}
                    disabled={isChatting}
                    className="h-9 text-xs bg-muted/30 focus-visible:ring-primary"
                  />
                  <Button
                    type="submit"
                    disabled={isChatting || !chatQuery.trim()}
                    className="h-9 px-3 gap-1.5 text-xs bg-primary hover:bg-primary/90 text-primary-foreground font-medium shrink-0"
                  >
                    <Send className="h-3.5 w-3.5" />
                    <span>Send</span>
                  </Button>
                </form>
                <div className="mt-1.5 flex items-center justify-between text-[10px] text-muted-foreground">
                  <span>Press Enter to send. Strictly grounded on {activeDataset.title}.</span>
                  {onNavigateToChat && (
                    <button
                      type="button"
                      onClick={() => onNavigateToChat(activeDataset.title)}
                      className="text-primary hover:underline"
                    >
                      Open in Global Enterprise Chat →
                    </button>
                  )}
                </div>
              </div>
            </Card>
          ) : (
            /* Empty State: No Dataset Selected */
            <Card className="border-border/80 bg-card/60 backdrop-blur-sm p-12 text-center space-y-3">
              <div className="h-12 w-12 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center text-primary mx-auto">
                <Database className="h-6 w-6" />
              </div>
              <h3 className="text-base font-semibold text-foreground">
                No Dataset Selected
              </h3>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                Select any indexed dataset from the list on the left, or upload a new file (PDF, DOC, PPT, CSV, TXT) to automatically launch its dedicated, individual chatbox.
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => quickFileInputRef.current?.click()}
                className="gap-2 text-xs"
              >
                <UploadCloud className="h-3.5 w-3.5 text-primary" />
                Upload & Ingest File
              </Button>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
