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
  listNotes,
  getNoteDetail,
  deleteNote,
  parseFile,
  studyDocument,
  createVaultNote,
  type NoteSummary,
  type NoteDetail,
} from "@/lib/api";
import { recordExchange } from "@/lib/conversationStore";
import {
  FileText,
  Tag,
  Calendar,
  Search,
  RefreshCw,
  Sparkles,
  BookOpen,
  Terminal,
  GraduationCap,
  UploadCloud,
  Send,
  CheckCircle2,
  FileCheck,
  Layers,
  ArrowRight,
  Bot,
  User,
  PlusCircle,
  FileQuestion,
  Lightbulb,
  Brain,
  Maximize,
  Maximize2,
  Minimize2,
  Columns,
  Crop,
  PanelLeftClose,
  PanelLeft,
  Trash2,
} from "lucide-react";
import { format12HrDateTime } from "@/lib/utils";

interface NotesProps {
  currentUserId?: string;
  currentTenantId?: string;
  onNavigateToChat?: (query: string) => void;
}

interface StudyDoc {
  id: string;
  filename: string;
  title: string;
  content: string;
  file_type: string;
  char_count: number;
  page_count: number;
  uploaded_at: string;
}

interface StudyMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  mode?: "qa" | "quiz" | "summary" | "explain";
  timestamp: string;
}

type ChatSizePreset = "compact" | "standard" | "large" | "full";

export function Notes({
  currentUserId = "alice",
  currentTenantId = "corp-default",
  onNavigateToChat,
}: NotesProps) {
  // Navigation between Vault and Study Hub
  const [activeSection, setActiveSection] = React.useState<"study" | "vault">("study");

  // --- Local Vault State ---
  const [notes, setNotes] = React.useState<NoteSummary[]>([]);
  const [selectedSlug, setSelectedSlug] = React.useState<string | null>(null);
  const [selectedNote, setSelectedNote] = React.useState<NoteDetail | null>(null);
  const [selectedTag, setSelectedTag] = React.useState<string | null>(null);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = React.useState(false);

  // --- Study & Learning Hub State ---
  // Persistent list of uploaded study documents
  const [studyDocs, setStudyDocs] = React.useState<StudyDoc[]>(() => {
    try {
      const saved = localStorage.getItem("aegismind_study_docs");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const [activeDocId, setActiveDocId] = React.useState<string | null>(() => {
    try {
      const saved = localStorage.getItem("aegismind_active_study_doc");
      return saved || null;
    } catch {
      return null;
    }
  });

  // Dedicated, individual conversation history per document
  const [docConversations, setDocConversations] = React.useState<Record<string, StudyMessage[]>>(() => {
    try {
      const saved = localStorage.getItem("aegismind_study_conversations");
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  const [isParsingDoc, setIsParsingDoc] = React.useState(false);
  const [studyQuery, setStudyQuery] = React.useState("");
  const [isStudying, setIsStudying] = React.useState(false);
  const [saveStatus, setSaveStatus] = React.useState<string | null>(null);
  const [memorySyncNotice, setMemorySyncNotice] = React.useState<string | null>(null);
  const [showDocPreview, setShowDocPreview] = React.useState(false);

  // Sizing & Crop Controls for Chatbox
  const [isSidebarCropped, setIsSidebarCropped] = React.useState(false);
  const [chatSizePreset, setChatSizePreset] = React.useState<ChatSizePreset>("standard");
  const [isChatExpandedHeight, setIsChatExpandedHeight] = React.useState(false);

  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const messagesEndRef = React.useRef<HTMLDivElement>(null);

  // Sync studyDocs to localStorage
  React.useEffect(() => {
    try {
      localStorage.setItem("aegismind_study_docs", JSON.stringify(studyDocs));
    } catch {
      // Ignored
    }
  }, [studyDocs]);

  // Sync docConversations to localStorage
  React.useEffect(() => {
    try {
      localStorage.setItem("aegismind_study_conversations", JSON.stringify(docConversations));
    } catch {
      // Ignored
    }
  }, [docConversations]);

  // Sync activeDocId to localStorage
  React.useEffect(() => {
    if (activeDocId) {
      try {
        localStorage.setItem("aegismind_active_study_doc", activeDocId);
      } catch {
        // Ignored
      }
    }
  }, [activeDocId]);

  // Set default active document if none selected
  React.useEffect(() => {
    if (studyDocs.length > 0 && (!activeDocId || !studyDocs.some((d) => d.id === activeDocId))) {
      setActiveDocId(studyDocs[0]!.id);
    }
  }, [studyDocs, activeDocId]);

  // Active document object
  const activeDoc = React.useMemo(() => {
    return studyDocs.find((d) => d.id === activeDocId) || null;
  }, [studyDocs, activeDocId]);

  // Current individual document messages
  const activeMessages = React.useMemo(() => {
    if (!activeDocId) return [];
    return docConversations[activeDocId] || [];
  }, [activeDocId, docConversations]);

  // Auto-scroll chat messages
  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeMessages, isStudying]);

  // Fetch local vault notes
  const fetchNotes = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listNotes(selectedTag || undefined);
      setNotes(data);
      if (data.length > 0 && !selectedSlug && data[0]) {
        setSelectedSlug(data[0].slug);
      }
    } catch {
      // Ignored
    } finally {
      setIsLoading(false);
    }
  }, [selectedTag, selectedSlug]);

  React.useEffect(() => {
    fetchNotes();
  }, [fetchNotes]);

  React.useEffect(() => {
    if (!selectedSlug) {
      setSelectedNote(null);
      return;
    }
    setIsLoadingDetail(true);
    getNoteDetail(selectedSlug)
      .then((detail) => setSelectedNote(detail))
      .catch(() => setSelectedNote(null))
      .finally(() => setIsLoadingDetail(false));
  }, [selectedSlug]);

  const allTags = React.useMemo(() => {
    const tagSet = new Set<string>();
    notes.forEach((n) => n.tags.forEach((t) => tagSet.add(t)));
    return Array.from(tagSet);
  }, [notes]);

  const filteredNotes = React.useMemo(() => {
    if (!searchQuery.trim()) return notes;
    const q = searchQuery.toLowerCase();
    return notes.filter(
      (n) =>
        n.title.toLowerCase().includes(q) ||
        n.preview.toLowerCase().includes(q) ||
        n.tags.some((t) => t.toLowerCase().includes(q))
    );
  }, [notes, searchQuery]);

  // Delete a note from the markdown vault
  const handleDeleteNote = async (slugToDelete: string, e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation();
    }
    const confirmed = window.confirm(`Are you sure you want to delete this note: ${slugToDelete}?`);
    if (!confirmed) return;

    try {
      await deleteNote(slugToDelete);
      setNotes((prev) => prev.filter((n) => n.slug !== slugToDelete));
      if (selectedSlug === slugToDelete) {
        const remaining = notes.filter((n) => n.slug !== slugToDelete);
        setSelectedSlug(remaining.length > 0 ? remaining[0]!.slug : null);
        if (remaining.length === 0) {
          setSelectedNote(null);
        }
      }
    } catch (err) {
      console.error("Failed to delete note:", err);
    }
  };


  // Handle Study File Upload (PDF, PPT, DOCX, etc.)
  const handleStudyFileUpload = async (file: File) => {
    setIsParsingDoc(true);
    setSaveStatus(null);
    try {
      const parsed = await parseFile(file);
      const newDocId = `doc-${Date.now()}`;
      const newDoc: StudyDoc = {
        id: newDocId,
        filename: parsed.filename,
        title: parsed.title,
        content: parsed.content,
        file_type: parsed.file_type,
        char_count: parsed.char_count,
        page_count: parsed.page_count,
        uploaded_at: new Date().toLocaleTimeString(),
      };

      const countLabel =
        parsed.page_count > 1
          ? `${parsed.page_count} ${parsed.file_type.includes("presentation") || parsed.filename.match(/\.(ppt|pptx)$/i) ? "slides" : "pages"}`
          : "1 document";

      const welcomeMsg: StudyMessage = {
        id: `msg-${Date.now()}`,
        role: "assistant",
        content: `I have extracted **${newDoc.title}** (${countLabel}, ${parsed.char_count.toLocaleString()} characters). I am your dedicated study partner for this file! Ask me anything, click **Quiz Me** to test your knowledge, or ask me to explain difficult slides. Every turn is automatically preserved in long-term memory.`,
        mode: "qa",
        timestamp: "Just now",
      };

      setStudyDocs((prev) => [newDoc, ...prev]);
      setActiveDocId(newDocId);
      setDocConversations((prev) => ({
        ...prev,
        [newDocId]: [welcomeMsg],
      }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to parse document";
      setSaveStatus(`Extraction failed: ${msg}`);
    } finally {
      setIsParsingDoc(false);
    }
  };

  // Run a study interaction in the active document's dedicated chatbox
  const executeStudyAction = async (queryText: string, mode: "qa" | "quiz" | "summary" | "explain" = "qa") => {
    if (!activeDoc || isStudying) return;
    const currentDocId = activeDoc.id;

    const userMsg: StudyMessage = {
      id: `usr-${Date.now()}`,
      role: "user",
      content: queryText,
      mode,
      timestamp: "Just now",
    };

    setDocConversations((prev) => ({
      ...prev,
      [currentDocId]: [...(prev[currentDocId] || []), userMsg],
    }));
    setStudyQuery("");
    setIsStudying(true);

    try {
      const res = await studyDocument({
        title: activeDoc.title,
        content: activeDoc.content,
        query: queryText,
        mode,
        user_id: currentUserId,
        tenant_id: currentTenantId,
      });

      const assistantMsg: StudyMessage = {
        id: `asst-${Date.now()}`,
        role: "assistant",
        content: res.answer,
        mode,
        timestamp: new Date().toISOString(),
      };

      setDocConversations((prev) => ({
        ...prev,
        [currentDocId]: [...(prev[currentDocId] || []), assistantMsg],
      }));

      // Persist to cross-chatbox conversation store for Memory aggregation
      recordExchange({
        threadId: `notes-${currentDocId}`,
        label: `Notes: ${activeDoc.title}`,
        source: "notes",
        userMessage: {
          id: userMsg.id,
          content: queryText,
          timestamp: new Date().toISOString(),
        },
        assistantMessage: {
          id: assistantMsg.id,
          content: res.answer,
          timestamp: new Date().toISOString(),
        },
      });

      // Flash confirmation that turn was preserved in long-term memory
      setMemorySyncNotice("Preserved in Long-Term Memory");
      setTimeout(() => setMemorySyncNotice(null), 3500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Study request failed";
      setDocConversations((prev) => ({
        ...prev,
        [currentDocId]: [
          ...(prev[currentDocId] || []),
          {
            id: `err-${Date.now()}`,
            role: "assistant",
            content: `Error generating response: ${msg}. Please try again or rephrase your question.`,
            timestamp: "Just now",
          },
        ],
      }));
    } finally {
      setIsStudying(false);
    }
  };

  // Clear chat history for the active document only
  const handleClearCurrentChat = () => {
    if (!activeDocId) return;
    setDocConversations((prev) => {
      const copy = { ...prev };
      delete copy[activeDocId];
      return copy;
    });
  };

  // Delete document and its dedicated conversation
  const handleDeleteDoc = (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setStudyDocs((prev) => prev.filter((d) => d.id !== docId));
    setDocConversations((prev) => {
      const copy = { ...prev };
      delete copy[docId];
      return copy;
    });
    if (activeDocId === docId) {
      const remaining = studyDocs.filter((d) => d.id !== docId);
      setActiveDocId(remaining[0]?.id || null);
    }
  };

  // Save current study session into Sovereign Notes Vault
  const handleSaveToVault = async () => {
    if (!activeDoc || activeMessages.length === 0) return;
    try {
      const conversationText = activeMessages
        .map((m) => `### ${m.role === "user" ? "User Question" : "Study Partner"}\n\n${m.content}`)
        .join("\n\n---\n\n");

      const noteContent = `# Study Guide: ${activeDoc.title}\n\n**Source File:** \`${activeDoc.filename}\` (${activeDoc.char_count} chars)\n**Study Date:** ${new Date().toLocaleDateString()}\n**Long-Term Memory:** Synchronized\n\n---\n\n${conversationText}`;

      await createVaultNote({
        title: `Study: ${activeDoc.title}`,
        content: noteContent,
        tags: ["study", "learning", activeDoc.file_type || "document"],
        source_query: `Study session for ${activeDoc.title}`,
      });

      setSaveStatus(`Saved study guide for "${activeDoc.title}" to local notes vault!`);
      await fetchNotes();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to save note";
      setSaveStatus(`Could not save note: ${msg}`);
    }
  };

  // Calculate layout column span based on crop & size settings
  const isFullWidth = isSidebarCropped || chatSizePreset === "full";
  const leftColSpanClass = isFullWidth
    ? "hidden"
    : chatSizePreset === "large"
    ? "lg:col-span-3"
    : chatSizePreset === "compact"
    ? "lg:col-span-5"
    : "lg:col-span-4";

  const rightColSpanClass = isFullWidth
    ? "lg:col-span-12"
    : chatSizePreset === "large"
    ? "lg:col-span-9"
    : chatSizePreset === "compact"
    ? "lg:col-span-7"
    : "lg:col-span-8";

  const chatHeightClass = isChatExpandedHeight
    ? "min-h-[750px] max-h-[calc(100vh-14rem)]"
    : "min-h-[580px] max-h-[calc(100vh-22rem)]";

  return (
    <div className="flex-1 p-6 max-w-7xl mx-auto w-full space-y-6">
      {/* Top Header & Section Switcher */}
      <div className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl p-5 shadow-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
              <BookOpen className="h-6 w-6 text-primary" />
              Notes & Learning Hub
            </h1>
            <Badge variant="outline" className="border-primary/40 text-primary text-xs">
              Sovereign AI
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Personal offline knowledge vault and interactive LLM study partner for PDFs, presentations, slides, and documents.
          </p>
        </div>

        {/* Section Tabs: Study Hub vs Vault Notes */}
        <div className="flex items-center gap-2 bg-muted/40 p-1 rounded-lg border border-border/60">
          <button
            type="button"
            onClick={() => setActiveSection("study")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeSection === "study"
                ? "bg-primary text-primary-foreground shadow-xs"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            <GraduationCap className="h-3.5 w-3.5" />
            <span>Study Hub (PDF / Slides)</span>
            <Badge variant="secondary" className="ml-1 text-[9px] px-1 py-0 bg-background/20 text-inherit">
              Individual Chats
            </Badge>
          </button>
          <button
            type="button"
            onClick={() => setActiveSection("vault")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeSection === "vault"
                ? "bg-primary text-primary-foreground shadow-xs"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            <BookOpen className="h-3.5 w-3.5" />
            <span>Vault Notes ({notes.length})</span>
          </button>
        </div>
      </div>

      {/* --- SECTION 1: STUDY & LEARNING HUB --- */}
      {activeSection === "study" && (
        <div className="space-y-4">
          {/* Quick Toolbar & Sizing Controls Bar */}
          <div className="flex items-center justify-between gap-2 rounded-xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl px-4 py-2.5 text-xs shadow-md">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-foreground flex items-center gap-1 text-[11px]">
                <Layers className="h-3.5 w-3.5 text-primary" />
                Active Files:
              </span>
              <span className="text-muted-foreground text-[11px]">
                {studyDocs.length > 0
                  ? `${studyDocs.length} loaded with dedicated chatboxes`
                  : "Upload any PDF or PPT slide deck to start"}
              </span>
            </div>

            {/* Sizing & View Controls */}
            <div className="flex items-center gap-1.5">
              {/* Toggle Document Sidebar */}
              <Button
                variant={isSidebarCropped ? "default" : "outline"}
                size="sm"
                onClick={() => setIsSidebarCropped(!isSidebarCropped)}
                title={isSidebarCropped ? "Show documents sidebar" : "Hide documents sidebar (Enlarge chatbox)"}
                className="h-7 w-7 p-0"
              >
                {isSidebarCropped ? (
                  <PanelLeft className="h-3.5 w-3.5" />
                ) : (
                  <PanelLeftClose className="h-3.5 w-3.5" />
                )}
              </Button>

              {/* Chatbox Size Toggle (Icons only: Compact, Standard, Enlarged, Full Width) */}
              <div className="hidden sm:flex items-center gap-1 border-l border-border/60 pl-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setIsSidebarCropped(false);
                    setChatSizePreset("compact");
                  }}
                  title="Compact View"
                  className={`h-7 w-7 flex items-center justify-center rounded transition-colors ${
                    !isSidebarCropped && chatSizePreset === "compact"
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <Minimize2 className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsSidebarCropped(false);
                    setChatSizePreset("standard");
                  }}
                  title="Standard View"
                  className={`h-7 w-7 flex items-center justify-center rounded transition-colors ${
                    !isSidebarCropped && chatSizePreset === "standard"
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <Columns className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsSidebarCropped(false);
                    setChatSizePreset("large");
                  }}
                  title="Enlarged View"
                  className={`h-7 w-7 flex items-center justify-center rounded transition-colors ${
                    !isSidebarCropped && chatSizePreset === "large"
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <Maximize2 className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsSidebarCropped(true);
                    setChatSizePreset("full");
                  }}
                  title="Full Width View"
                  className={`h-7 w-7 flex items-center justify-center rounded transition-colors ${
                    isSidebarCropped || chatSizePreset === "full"
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <Maximize className="h-3.5 w-3.5" />
                </button>
              </div>

              {/* Maximize / Height Expander */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  const nextHeight = !isChatExpandedHeight;
                  setIsChatExpandedHeight(nextHeight);
                  if (nextHeight) {
                    setIsSidebarCropped(true);
                  }
                }}
                title={isChatExpandedHeight ? "Decrease Chatbox Size" : "Enlarge / Maximize Chatbox"}
                className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
              >
                {isChatExpandedHeight ? (
                  <Minimize2 className="h-3.5 w-3.5 text-primary" />
                ) : (
                  <Maximize2 className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
          </div>

          {/* Main 2-Column or Enlarged Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left Column: Document Upload & List (Can be cropped) */}
            <div className={`${leftColSpanClass} flex flex-col space-y-4`}>
              {/* File Upload Drop Area */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const file = e.dataTransfer.files?.[0];
                  if (file) handleStudyFileUpload(file);
                }}
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-primary/40 hover:border-primary/80 bg-primary/5 hover:bg-primary/10 rounded-xl p-4 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-1.5 group shadow-xs"
              >
                <div className="h-9 w-9 rounded-full bg-primary/20 flex items-center justify-center text-primary group-hover:scale-105 transition-transform">
                  {isParsingDoc ? (
                    <RefreshCw className="h-4 w-4 animate-spin" />
                  ) : (
                    <UploadCloud className="h-4 w-4" />
                  )}
                </div>
                <div>
                  <h3 className="text-xs font-bold text-foreground">
                    {isParsingDoc ? "Extracting Slides / Pages..." : "Upload Study Material"}
                  </h3>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Drop PDF, PowerPoint (.ppt, .pptx), Word (.docx), or slides
                  </p>
                </div>
                <Badge variant="outline" className="text-[10px] border-primary/30 text-primary">
                  Separate Chatbox per File
                </Badge>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="*/*"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleStudyFileUpload(file);
                  }}
                  className="hidden"
                />
              </div>

              {/* Loaded Study Documents List */}
              <Card className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl flex-1 flex flex-col shadow-xl">
                <CardHeader className="py-2.5 px-3.5 border-b border-border/50">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-xs font-bold text-foreground flex items-center gap-1.5">
                      <Layers className="h-3.5 w-3.5 text-primary" />
                      Active Files ({studyDocs.length})
                    </CardTitle>
                    {studyDocs.length > 0 && (
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="text-[10px] text-primary hover:underline flex items-center gap-0.5 font-medium"
                      >
                        <PlusCircle className="h-3 w-3" /> Add More
                      </button>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="p-2 space-y-1.5 max-h-[260px] overflow-y-auto">
                  {studyDocs.length === 0 ? (
                    <div className="py-6 text-center text-muted-foreground">
                      <GraduationCap className="h-8 w-8 mx-auto text-muted-foreground/40 mb-1.5" />
                      <p className="text-xs font-medium text-foreground">No documents loaded yet</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        Upload lecture slides or technical documents to start studying.
                      </p>
                    </div>
                  ) : (
                    studyDocs.map((doc) => {
                      const isSelected = activeDocId === doc.id;
                      const msgCount = (docConversations[doc.id] || []).length;
                      return (
                        <div
                          key={doc.id}
                          onClick={() => setActiveDocId(doc.id)}
                          className={`w-full text-left p-2.5 rounded-lg border transition-all cursor-pointer relative group ${
                            isSelected
                              ? "bg-secondary border-primary/50 shadow-xs"
                              : "bg-card/30 border-border/50 hover:bg-muted/40"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-1 pr-6">
                            <span className="font-semibold text-xs text-foreground truncate">
                              {doc.title}
                            </span>
                            <Badge variant="outline" className="text-[9px] px-1 py-0 uppercase shrink-0 border-border">
                              {doc.file_type}
                            </Badge>
                          </div>
                          <div className="flex items-center justify-between text-[10px] text-muted-foreground mt-1">
                            <span>
                              {doc.page_count > 1 ? `${doc.page_count} slides/pages` : "1 doc"} • {doc.char_count.toLocaleString()} chars
                            </span>
                            <Badge variant="secondary" className="text-[9px] px-1 py-0 bg-muted text-primary font-mono">
                              {msgCount} {msgCount === 1 ? "turn" : "turns"}
                            </Badge>
                          </div>

                          {/* Delete Document Button */}
                          <button
                            type="button"
                            onClick={(e) => handleDeleteDoc(doc.id, e)}
                            title="Remove file and chat"
                            className="absolute right-2 top-2.5 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      );
                    })
                  )}
                </CardContent>
              </Card>

              {/* Document Overview & Quick Study Actions */}
              {activeDoc && (
                <Card className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl p-4 space-y-3 shadow-xl">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground truncate">
                      Study Actions: {activeDoc.title}
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowDocPreview(!showDocPreview)}
                      className="text-[10px] text-primary hover:underline font-medium"
                    >
                      {showDocPreview ? "Hide Preview" : "View Text"}
                    </button>
                  </div>

                  {showDocPreview && (
                    <div className="p-2.5 rounded-md bg-muted/40 border border-border/60 text-[11px] font-mono max-h-40 overflow-y-auto whitespace-pre-wrap text-foreground/80">
                      {activeDoc.content.slice(0, 2000)}
                      {activeDoc.content.length > 2000 && "\n\n... [Truncated for preview]"}
                    </div>
                  )}

                  {/* High-yield study action buttons */}
                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => executeStudyAction("Generate an interactive study quiz on key concepts.", "quiz")}
                      disabled={isStudying}
                      className="text-[11px] h-8 flex items-center justify-center gap-1.5 border-primary/30 hover:bg-primary/10 text-primary font-medium"
                    >
                      <FileQuestion className="h-3.5 w-3.5" />
                      <span>Quiz Me</span>
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => executeStudyAction("Explain the core concepts and mental models in simple terms.", "explain")}
                      disabled={isStudying}
                      className="text-[11px] h-8 flex items-center justify-center gap-1.5 border-emerald-500/30 hover:bg-emerald-500/10 text-emerald-400 font-medium"
                    >
                      <Lightbulb className="h-3.5 w-3.5" />
                      <span>Explain Concepts</span>
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => executeStudyAction("Summarize the key takeaways and main points by slide/page.", "summary")}
                      disabled={isStudying}
                      className="text-[11px] h-8 flex items-center justify-center gap-1.5 border-blue-500/30 hover:bg-blue-500/10 text-blue-400 font-medium"
                    >
                      <FileCheck className="h-3.5 w-3.5" />
                      <span>Summary</span>
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleSaveToVault}
                      disabled={activeMessages.length === 0}
                      className="text-[11px] h-8 flex items-center justify-center gap-1.5 border-amber-500/30 hover:bg-amber-500/10 text-amber-400 font-medium"
                    >
                      <BookOpen className="h-3.5 w-3.5" />
                      <span>Save to Vault</span>
                    </Button>
                  </div>

                  {saveStatus && (
                    <div className="p-2 rounded-md bg-primary/10 border border-primary/30 text-[11px] text-primary flex items-center gap-1.5 animate-in fade-in">
                      <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                      <span>{saveStatus}</span>
                    </div>
                  )}

                  {onNavigateToChat && (
                    <button
                      type="button"
                      onClick={() => onNavigateToChat(`Regarding my study document "${activeDoc.title}": `)}
                      className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1 w-full justify-center pt-1"
                    >
                      <span>Continue discussion in Enterprise Chat</span>
                      <ArrowRight className="h-3 w-3" />
                    </button>
                  )}
                </Card>
              )}
            </div>

            {/* Right Column: Dedicated Individual Chatbox for the Selected Document */}
            <div className={`${rightColSpanClass} flex flex-col transition-all duration-200`}>
              <Card className={`flex-1 flex flex-col rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl overflow-hidden shadow-xl ${chatHeightClass}`}>
                {/* Chat Session Header */}
                <CardHeader className="py-2.5 px-4 border-b border-border/60 bg-muted/20 flex flex-row items-center justify-between">
                  <div className="flex items-center gap-2 truncate">
                    <GraduationCap className="h-4 w-4 text-primary shrink-0" />
                    <span className="font-bold text-xs text-foreground truncate">
                      {activeDoc ? `Study Session: ${activeDoc.title}` : "Interactive Study Partner"}
                    </span>
                    {activeDoc && (
                      <Badge variant="outline" className="text-[10px] border-primary/40 text-primary shrink-0">
                        {activeDoc.page_count > 1 ? `${activeDoc.page_count} slides/pages` : "1 doc"}
                      </Badge>
                    )}
                  </div>

                  {/* Header Actions: Long-Term Memory Badge, Clear, Resize */}
                  <div className="flex items-center gap-2 shrink-0">
                    {/* Long-Term Memory Badge */}
                    <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[10px] text-emerald-400 font-medium">
                      <Brain className="h-3 w-3 animate-pulse" />
                      <span>{memorySyncNotice || "Long-Term Memory Active"}</span>
                    </div>

                    {/* Sizing / Enlarge Toggle inside Chat Header */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setIsSidebarCropped(!isSidebarCropped)}
                      title={isSidebarCropped ? "Show left document panel" : "Crop left panel to enlarge chat"}
                      className="h-6 px-2 text-[10px] gap-1 text-muted-foreground hover:text-foreground border border-border/60"
                    >
                      {isSidebarCropped ? <PanelLeft className="h-3 w-3" /> : <PanelLeftClose className="h-3 w-3" />}
                      <span className="hidden sm:inline">{isSidebarCropped ? "Un-crop" : "Crop"}</span>
                    </Button>

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        const nextHeight = !isChatExpandedHeight;
                        setIsChatExpandedHeight(nextHeight);
                        if (nextHeight) setIsSidebarCropped(true);
                        else setIsSidebarCropped(false);
                      }}
                      title={isChatExpandedHeight ? "Decrease Chatbox Size" : "Enlarge Chatbox"}
                      className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
                    >
                      {isChatExpandedHeight ? <Minimize2 className="h-3 w-3 text-primary" /> : <Maximize2 className="h-3 w-3" />}
                    </Button>

                    {activeMessages.length > 0 && (
                      <button
                        type="button"
                        onClick={handleClearCurrentChat}
                        className="text-[10px] text-muted-foreground hover:text-destructive border border-border/40 px-2 py-0.5 rounded"
                      >
                        Clear Chat
                      </button>
                    )}
                  </div>
                </CardHeader>

                {/* Conversation Body: Dedicated to the active document */}
                <CardContent className="flex-1 p-4 overflow-y-auto space-y-4">
                  {activeMessages.length === 0 ? (
                    <div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-muted-foreground min-h-[320px]">
                      <GraduationCap className="h-12 w-12 text-muted-foreground/30 mb-3" />
                      <h3 className="text-sm font-semibold text-foreground">
                        {activeDoc ? `Ready to study "${activeDoc.title}"` : "Ready for Learning & Examination"}
                      </h3>
                      <p className="text-xs text-muted-foreground mt-1 max-w-md">
                        {activeDoc
                          ? "This document has its own dedicated chatbox. Ask questions, request quizzes, or review key concepts."
                          : "Upload or select a PDF, presentation slide deck, or document from the left to start."}
                      </p>
                    </div>
                  ) : (
                    activeMessages.map((msg) => {
                      const isUser = msg.role === "user";
                      return (
                        <div
                          key={msg.id}
                          className={`flex items-start gap-3 text-xs leading-relaxed ${
                            isUser ? "flex-row-reverse" : "flex-row"
                          }`}
                        >
                          <div
                            className={`h-7 w-7 rounded-full flex items-center justify-center shrink-0 ${
                              isUser
                                ? "bg-primary text-primary-foreground font-semibold"
                                : "bg-primary/20 border border-primary/40 text-primary"
                            }`}
                          >
                            {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                          </div>

                          <div
                            className={`rounded-xl p-3.5 max-w-[85%] space-y-2 shadow-xs ${
                              isUser
                                ? "bg-primary text-primary-foreground font-medium"
                                : "bg-secondary/70 border border-border/80 text-foreground"
                            }`}
                          >
                            <div className="prose prose-invert prose-xs max-w-none whitespace-pre-wrap font-sans">
                              {msg.content}
                            </div>
                            <div
                              className={`text-[10px] flex items-center justify-between gap-2 pt-1 border-t ${
                                isUser ? "border-primary-foreground/20 text-primary-foreground/70" : "border-border/40 text-muted-foreground"
                              }`}
                            >
                              <span>{msg.role === "assistant" ? "AegisMind Study Partner" : "You"}</span>
                              <div className="flex items-center gap-1.5">
                                <span>{msg.timestamp}</span>
                                <span className="text-[9px] text-emerald-400 font-mono">• Memory Stored</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}

                  {isStudying && (
                    <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/30 border border-border/50 text-xs text-muted-foreground">
                      <RefreshCw className="h-3.5 w-3.5 animate-spin text-primary" />
                      <span>Synthesizing educational response and committing to long-term memory...</span>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </CardContent>

                {/* Question Input Footer */}
                <div className="p-3 border-t border-border/60 bg-card/60 space-y-2">
                  {/* Suggested Study Queries */}
                  {activeDoc && (
                    <div className="flex flex-wrap gap-1.5 items-center">
                      <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                        <Sparkles className="h-3 w-3 text-primary" /> Suggested:
                      </span>
                      <button
                        type="button"
                        onClick={() => executeStudyAction("What are the key points in this document?", "qa")}
                        className="text-[10px] px-2 py-0.5 rounded-full bg-muted/40 hover:bg-muted text-muted-foreground border border-border/60 transition-colors"
                      >
                        Key points?
                      </button>
                      <button
                        type="button"
                        onClick={() => executeStudyAction("Test my knowledge with 3 challenging quiz questions", "quiz")}
                        className="text-[10px] px-2 py-0.5 rounded-full bg-muted/40 hover:bg-muted text-muted-foreground border border-border/60 transition-colors"
                      >
                        Quiz me on 3 questions
                      </button>
                      <button
                        type="button"
                        onClick={() => executeStudyAction("Explain the main formulas or technical requirements", "explain")}
                        className="text-[10px] px-2 py-0.5 rounded-full bg-muted/40 hover:bg-muted text-muted-foreground border border-border/60 transition-colors"
                      >
                        Technical requirements
                      </button>
                    </div>
                  )}

                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (studyQuery.trim()) {
                        executeStudyAction(studyQuery.trim(), "qa");
                      }
                    }}
                    className="flex items-center gap-2"
                  >
                    <Input
                      placeholder={
                        activeDoc
                          ? `Ask about ${activeDoc.title} or type your answer to the quiz...`
                          : "Upload a document or slide deck to start asking questions..."
                      }
                      value={studyQuery}
                      onChange={(e) => setStudyQuery(e.target.value)}
                      disabled={!activeDoc || isStudying}
                      className="h-9 text-xs"
                    />
                    <Button
                      type="submit"
                      disabled={!activeDoc || !studyQuery.trim() || isStudying}
                      className="h-9 px-4 text-xs font-semibold gap-1.5 shadow-xs"
                    >
                      <Send className="h-3.5 w-3.5" />
                      <span>Ask</span>
                    </Button>
                  </form>
                </div>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* --- SECTION 2: LOCAL VAULT NOTES --- */}
      {activeSection === "vault" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-xs text-muted-foreground">
              Showing markdown notes maintained locally in the Sovereign Vault.
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchNotes}
              disabled={isLoading}
              className="text-xs flex items-center gap-1.5"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin text-primary" : ""}`} />
              Refresh
            </Button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-[550px]">
            {/* Left Column: Note List & Filters */}
            <div className="lg:col-span-5 flex flex-col space-y-4">
              {/* Search & Tag Filter Bar */}
              <div className="space-y-3">
                <div className="relative">
                  <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder="Search local notes..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9 h-9 text-xs"
                  />
                </div>

                {/* Tag Pills */}
                {allTags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 items-center">
                    <span className="text-[11px] text-muted-foreground flex items-center gap-1 mr-1">
                      <Tag className="h-3 w-3" /> Tags:
                    </span>
                    <button
                      type="button"
                      onClick={() => setSelectedTag(null)}
                      className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                        selectedTag === null
                          ? "bg-primary text-primary-foreground border-primary"
                          : "bg-muted/40 text-muted-foreground border-border hover:bg-muted"
                      }`}
                    >
                      All ({notes.length})
                    </button>
                    {allTags.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => setSelectedTag(tag === selectedTag ? null : tag)}
                        className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                          selectedTag === tag
                            ? "bg-primary text-primary-foreground border-primary"
                            : "bg-muted/40 text-muted-foreground border-border hover:bg-muted"
                        }`}
                      >
                        #{tag}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Notes Scrollable List */}
              <div className="flex-1 overflow-y-auto space-y-2 pr-1 max-h-[calc(100vh-20rem)]">
                {filteredNotes.length === 0 ? (
                  <Card className="border-dashed border-border/80 bg-muted/10 p-6 text-center">
                    <FileText className="h-8 w-8 mx-auto text-muted-foreground/60 mb-2" />
                    <p className="text-xs font-medium text-foreground">No notes found</p>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Save a study guide from the Study Hub or ask the Sovereign Agent to create one.
                    </p>
                  </Card>
                ) : (
                  filteredNotes.map((note) => {
                    const isSelected = selectedSlug === note.slug;
                    return (
                      <button
                        key={note.slug}
                        type="button"
                        onClick={() => setSelectedSlug(note.slug)}
                        className={`w-full text-left p-3.5 rounded-lg border transition-all ${
                          isSelected
                            ? "bg-secondary border-primary/50 shadow-xs"
                            : "bg-card/40 border-border/70 hover:bg-muted/30"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="font-semibold text-xs text-foreground line-clamp-1">
                            {note.title}
                          </h3>
                          <button
                            type="button"
                            onClick={(e) => handleDeleteNote(note.slug, e)}
                            className="h-5 w-5 p-0.5 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors shrink-0"
                            title="Delete note from vault"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                        <p className="text-[11px] text-muted-foreground line-clamp-2 mt-1">
                          {note.preview}
                        </p>
                        <div className="flex items-center justify-between gap-2 mt-2 pt-2 border-t border-border/40 text-[10px] text-muted-foreground">
                          <div className="flex items-center gap-1">
                            <Calendar className="h-3 w-3" />
                            <span>{new Date(note.created_at).toLocaleDateString()}</span>
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {note.tags.map((t) => (
                              <span key={t} className="text-primary font-medium">
                                #{t}
                              </span>
                            ))}
                          </div>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Right Column: Note Preview & Detail */}
            <div className="lg:col-span-7 flex flex-col">
              <Card className="flex-1 flex flex-col border-border/80 bg-card/50 overflow-hidden">
                {isLoadingDetail ? (
                  <div className="flex-1 flex items-center justify-center p-12 text-muted-foreground text-xs">
                    <RefreshCw className="h-5 w-5 animate-spin text-primary mr-2" />
                    Loading note content...
                  </div>
                ) : selectedNote ? (
                  <div className="flex-1 flex flex-col">
                    <CardHeader className="border-b border-border/60 bg-muted/20 pb-4">
                      <div className="flex items-center justify-between gap-2">
                        <CardTitle className="text-lg font-bold text-foreground">
                          {selectedNote.title}
                        </CardTitle>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-[10px] border-border text-muted-foreground">
                            {selectedNote.slug}
                          </Badge>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteNote(selectedNote.slug)}
                            className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                            title="Delete note from vault"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                      {selectedNote.created_at && (
                        <CardDescription className="text-xs flex items-center gap-3 mt-1">
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3 w-3" />
                            {new Date(selectedNote.created_at).toLocaleString()}
                          </span>
                          {selectedNote.source_query && (
                            <span className="flex items-center gap-1 text-primary">
                              <Sparkles className="h-3 w-3" /> Query: {selectedNote.source_query}
                            </span>
                          )}
                        </CardDescription>
                      )}
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {selectedNote.tags.map((tag) => (
                          <Badge
                            key={tag}
                            variant="secondary"
                            className="text-[10px] bg-secondary/80 border-border text-foreground"
                          >
                            #{tag}
                          </Badge>
                        ))}
                      </div>
                    </CardHeader>
                    <CardContent className="flex-1 p-6 overflow-y-auto max-h-[calc(100vh-22rem)]">
                      <div className="prose prose-invert prose-xs max-w-none text-foreground/90 leading-relaxed whitespace-pre-wrap font-sans">
                        {selectedNote.content}
                      </div>
                    </CardContent>
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-muted-foreground">
                    <Terminal className="h-10 w-10 text-muted-foreground/40 mb-3" />
                    <h3 className="text-xs font-semibold text-foreground">Select a note to inspect</h3>
                    <p className="text-[11px] text-muted-foreground mt-1 max-w-sm">
                      Select a note from the vault sidebar to review frontmatter metadata and markdown content.
                    </p>
                  </div>
                )}
              </Card>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
