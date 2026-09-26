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
  ingestDocument,
  deleteDocument,
  listIndexedResources,
  listModels,
  type ModelInfo,
  type ResourceItem,
} from "@/lib/api";
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
} from "lucide-react";

interface DatasetsProps {
  currentTenantId: string;
  currentUserId: string;
  onNavigateToChat?: (query?: string) => void;
}

export function Datasets({
  currentTenantId,
  currentUserId,
  onNavigateToChat,
}: DatasetsProps) {
  // Form State
  const [title, setTitle] = React.useState("");
  const [content, setContent] = React.useState("");
  const [documentId, setDocumentId] = React.useState("");
  const [allowedUsers, setAllowedUsers] = React.useState<string[]>([currentUserId]);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [feedback, setFeedback] = React.useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Model & Resources State
  const [modelInfo, setModelInfo] = React.useState<ModelInfo | null>(null);
  const [selectedModel, setSelectedModel] = React.useState<string>("");
  const [resources, setResources] = React.useState<ResourceItem[]>([]);
  const [searchFilter, setSearchFilter] = React.useState("");
  const [isLoadingResources, setIsLoadingResources] = React.useState(false);
  const [isDeleting, setIsDeleting] = React.useState<string | null>(null);

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const availablePrincipals = [
    { id: "alice", label: "alice (eng)" },
    { id: "bob", label: "bob (contractor)" },
    { id: "charlie", label: "charlie (finance)" },
    { id: "*", label: "* (all tenant members)" },
  ];

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

  const togglePrincipal = (principalId: string) => {
    setAllowedUsers((prev) => {
      if (prev.includes(principalId)) {
        return prev.filter((p) => p !== principalId);
      }
      return [...prev, principalId];
    });
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!title) {
      const cleanName = file.name.replace(/\.[^/.]+$/, "");
      setTitle(cleanName);
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result;
      if (typeof text === "string") {
        setContent(text);
      }
    };
    reader.readAsText(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
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

      setFeedback({
        type: "success",
        message: `Successfully indexed "${res.title}" with ${res.chunk_count} vector chunks. Zanzibar permissions granted to: ${res.allowed_users.join(", ")}.`,
      });

      // Reset form
      setTitle("");
      setContent("");
      setDocumentId("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      // Refresh resource list
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

  const handleDelete = async (docId: string, docTitle: string) => {
    if (!confirm(`Are you sure you want to delete and revoke "${docTitle}"?`)) {
      return;
    }

    setIsDeleting(docId);
    try {
      await deleteDocument(docId);
      setFeedback({
        type: "success",
        message: `Dataset "${docTitle}" deleted and Zanzibar access tuples revoked.`,
      });
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

  const filteredResources = resources.filter((res) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return (
      res.title.toLowerCase().includes(q) ||
      res.id.toLowerCase().includes(q) ||
      res.connector.toLowerCase().includes(q)
    );
  });

  return (
    <div className="p-4 max-w-7xl mx-auto w-full space-y-6">
      {/* Top Banner: Ollama & LLM Status */}
      <Card className="border-border/80 bg-card/60 backdrop-blur-sm">
        <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-primary/10 border border-primary/30 flex items-center justify-center text-primary">
              <Cpu className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground">
                  Local Ollama LLM Engine
                </h3>
                <Badge
                  variant="outline"
                  className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[10px]"
                >
                  Online
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground">
                Connected via host gateway. Queries are synthesized using your local
                Ollama weights with verified Zanzibar access controls.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Active Model:</span>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="bg-secondary text-xs font-mono px-2.5 py-1.5 rounded-md border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer"
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
            <Button
              variant="outline"
              size="sm"
              onClick={fetchResourcesAndModels}
              className="h-8 px-2 text-xs"
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
          className={`p-3 rounded-lg text-xs flex items-center gap-2 border ${
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
          <span>{feedback.message}</span>
        </div>
      )}

      {/* Main Grid: Ingest Form on Left, Datasets List on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Dataset Ingest Form */}
        <div className="lg:col-span-5">
          <Card className="border-border/80 bg-card/60 backdrop-blur-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Database className="h-4 w-4 text-primary" />
                Ingest Custom Dataset
              </CardTitle>
              <CardDescription className="text-xs">
                Upload or paste structured records, guides, or documents. AegisMind
                chunks, embeds, and writes SpiceDB Zanzibar authorization tuples.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                {/* Title */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">
                    Dataset / Document Title <span className="text-primary">*</span>
                  </label>
                  <Input
                    placeholder="e.g. Project Apollo Q4 Architecture Plan"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    required
                    className="h-8 text-xs bg-muted/30"
                  />
                </div>

                {/* Optional Custom Resource ID */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground flex items-center justify-between">
                    <span>Custom Document ID (optional)</span>
                    <span className="font-mono text-[10px]">e.g. doc-apollo-01</span>
                  </label>
                  <Input
                    placeholder="Auto-generated if left blank"
                    value={documentId}
                    onChange={(e) => setDocumentId(e.target.value)}
                    className="h-8 text-xs font-mono bg-muted/30"
                  />
                </div>

                {/* Content Input or File Upload */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-foreground">
                      Document Content <span className="text-primary">*</span>
                    </label>
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="text-[11px] text-primary hover:underline flex items-center gap-1"
                    >
                      <UploadCloud className="h-3 w-3" />
                      Upload File (.txt, .md, .json)
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".txt,.md,.json,.csv,.log"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                  </div>
                  <textarea
                    rows={8}
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="Paste technical documentation, reports, meeting notes, or dataset records here..."
                    required
                    className="w-full rounded-md border border-input bg-muted/30 px-3 py-2 text-xs font-mono placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                  />
                  <div className="text-[10px] text-muted-foreground text-right">
                    {content.length} characters • ~{Math.ceil(content.length / 4)} tokens
                  </div>
                </div>

                {/* Zanzibar Access Control Configuration */}
                <div className="space-y-2 border-t border-border/60 pt-3">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                    <Lock className="h-3.5 w-3.5 text-emerald-400" />
                    <span>Zanzibar Access Authorization</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Select which users are granted SpiceDB viewer relation tuples for this
                    dataset. Other users will strictly receive zero data leakage.
                  </p>

                  <div className="grid grid-cols-2 gap-2 pt-1">
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
                          <span className="font-mono text-[11px]">{p.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Submit Button */}
                <Button
                  type="submit"
                  disabled={isSubmitting || !title.trim() || !content.trim()}
                  className="w-full gap-2 text-xs h-9 mt-2"
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      Chunking, Embedding & Securing...
                    </>
                  ) : (
                    <>
                      <UploadCloud className="h-3.5 w-3.5" />
                      Ingest & Index Dataset
                    </>
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Indexed Datasets & Document Repository */}
        <div className="lg:col-span-7 space-y-4">
          <Card className="border-border/80 bg-card/60 backdrop-blur-sm">
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <FileText className="h-4 w-4 text-emerald-400" />
                  Indexed Datasets & Documents
                </CardTitle>
                <CardDescription className="text-xs">
                  Active corpus indexed with vector embeddings and Zanzibar viewer
                  relations.
                </CardDescription>
              </div>
              <Badge variant="outline" className="font-mono text-xs">
                {filteredResources.length} Indexed
              </Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* Search filter */}
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  placeholder="Filter datasets by title or resource ID..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  className="pl-8 h-8 text-xs bg-muted/30"
                />
              </div>

              {/* Resource List */}
              <div className="space-y-2.5 max-h-[520px] overflow-y-auto pr-1">
                {isLoadingResources && filteredResources.length === 0 ? (
                  <div className="p-8 text-center text-xs text-muted-foreground">
                    <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-primary" />
                    Loading indexed datasets...
                  </div>
                ) : filteredResources.length === 0 ? (
                  <div className="p-8 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
                    No indexed datasets found. Ingest your first dataset using the form on the
                    left.
                  </div>
                ) : (
                  filteredResources.map((res) => (
                    <div
                      key={res.id}
                      className="p-3 rounded-lg border border-border/70 bg-card/40 hover:bg-card/80 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-xs text-foreground">
                            {res.title}
                          </span>
                          <Badge
                            variant="secondary"
                            className="text-[10px] font-mono py-0 h-4"
                          >
                            {res.connector || "custom_dataset"}
                          </Badge>
                        </div>
                        <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                          <span className="font-mono text-[10px] text-muted-foreground">
                            {res.id}
                          </span>
                          <span>•</span>
                          <span>{res.chunk_count ?? 1} chunks</span>
                          {res.allowed_users && res.allowed_users.length > 0 && (
                            <>
                              <span>•</span>
                              <span className="flex items-center gap-1">
                                <Users className="h-3 w-3 text-emerald-400" />
                                <span className="font-mono text-[10px]">
                                  {res.allowed_users.join(", ")}
                                </span>
                              </span>
                            </>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {onNavigateToChat && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onNavigateToChat(res.title)}
                            className="h-7 text-xs gap-1"
                            title="Query this document in Chat"
                          >
                            <MessageSquare className="h-3 w-3 text-primary" />
                            Chat
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={isDeleting === res.id}
                          onClick={() => handleDelete(res.id, res.title)}
                          className="h-7 text-xs text-destructive hover:text-destructive hover:bg-destructive/10 px-2"
                          title="Revoke Zanzibar access and delete vector chunks"
                        >
                          {isDeleting === res.id ? (
                            <RefreshCw className="h-3 w-3 animate-spin" />
                          ) : (
                            <Trash2 className="h-3 w-3" />
                          )}
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
