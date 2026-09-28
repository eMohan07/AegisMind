import * as React from "react";
import { Chat } from "@/components/Chat";
import { Connectors } from "@/components/Connectors";
import { Datasets } from "@/components/Datasets";
import { Notes } from "@/components/Notes";
import { KnowledgeGraph } from "@/components/graph/KnowledgeGraph";
import { Memory } from "@/components/Memory";
import { CommandPalette } from "@/components/CommandPalette";
import { ResourcePicker } from "@/components/ResourcePicker";
import {
  MessageSquare,
  Share2,
  FolderPlus,
  Database,
  BookOpen,
  Terminal,
  GitBranch,
  Brain,
  ArrowLeft,
  X,
  PanelLeft,
  ChevronRight,
  Sun,
  Moon,
  Search,
  HelpCircle,
  Sparkles,
  ExternalLink,
} from "lucide-react";

type ActiveTab =
  | "chat"
  | "connectors"
  | "datasets"
  | "notes"
  | "graph"
  | "memory";

interface NavItem {
  id: ActiveTab;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description?: string;
}

const SIDEBAR_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Core",
    items: [
      {
        id: "chat",
        label: "AI Chat",
        icon: MessageSquare,
        description: "Sovereign AI assistant & tool execution",
      },
      {
        id: "connectors",
        label: "Local Sources",
        icon: Share2,
        description: "Enterprise data source integrations",
      },
    ],
  },
  {
    title: "Knowledge & Study",
    items: [
      {
        id: "datasets",
        label: "Datasets & Files",
        icon: Database,
        description: "Study hub, multi-format PDFs, PPTs, tables",
      },
      {
        id: "notes",
        label: "Notes & Canvas",
        icon: BookOpen,
        description: "Document notes & per-document AI chat",
      },
      {
        id: "graph",
        label: "Knowledge Graph",
        icon: GitBranch,
        description: "Entity relationships & graph query engine",
      },
      {
        id: "memory",
        label: "Memory Recall",
        icon: Brain,
        description: "Episodic conversation & semantic storage",
      },
    ],
  },
];

const TAB_LABELS: Record<ActiveTab, string> = {
  chat: "Chat",
  connectors: "Local Sources",
  datasets: "Datasets",
  notes: "Notes",
  graph: "Knowledge Graph",
  memory: "Memory",
};

interface FAQItem {
  id: string;
  category: string;
  question: string;
  answer: string;
  targetTab?: ActiveTab;
}

const FAQ_ITEMS: FAQItem[] = [
  {
    id: "faq-1",
    category: "Overview",
    question: "What is AegisMind Sovereign Second Brain?",
    answer:
      "AegisMind is a fully sovereign enterprise intelligence system that runs locally. It indexes documents, executes autonomous system tools, and stores conversation memory on-premise with zero cloud data leakage.",
    targetTab: "chat",
  },
  {
    id: "faq-2",
    category: "Privacy",
    question: "Are my files, chats, or queries sent to external clouds?",
    answer:
      "No. AegisMind runs 100% locally with sovereign LLMs (such as Llama 3 via Ollama) and local vector embeddings. No queries or document data leave your machine.",
  },
  {
    id: "faq-3",
    category: "Sources",
    question: "What are Local Sources and how do Connectors work?",
    answer:
      "Local Sources connect your filesystem folders, personal datasets, and local databases directly to the RAG vector search engine for real-time retrieval in Chat.",
    targetTab: "connectors",
  },
  {
    id: "faq-4",
    category: "Memory",
    question: "How does Conversation Memory Recall work?",
    answer:
      "AegisMind automatically consolidates episodic knowledge across all chatboxes. Click the 'Memory Recall' button in Chat to recall facts, decisions, and past discussions anytime.",
    targetTab: "memory",
  },
  {
    id: "faq-6",
    category: "Ingest",
    question: "How do I ingest and index PDFs, PPTs, or documents?",
    answer:
      "Click the 'Ingest' button in the header or use 'Datasets & Files' to upload multi-format documents (PDFs, PPTs, tables, code) for instant chunking and vector indexing.",
    targetTab: "datasets",
  },
  {
    id: "faq-7",
    category: "Graph",
    question: "What is the Knowledge Graph engine?",
    answer:
      "The Knowledge Graph maps relationship entities across your documents, showing interconnected nodes and semantic linkages across your entire enterprise knowledge base.",
    targetTab: "graph",
  },
];

export function App() {
  const [activeTab, setActiveTab] = React.useState<ActiveTab>("chat");
  const [isDockExpanded, setIsDockExpanded] = React.useState(false);
  const [currentTenantId] = React.useState("corp-default");
  const [currentUserId] = React.useState("alice");
  const [isCommandOpen, setIsCommandOpen] = React.useState(false);
  const [isResourcePickerOpen, setIsResourcePickerOpen] = React.useState(false);
  const [initialChatQuery, setInitialChatQuery] = React.useState<string | undefined>(undefined);

  // FAQ Search dropdown state
  const [faqSearchQuery, setFaqSearchQuery] = React.useState("");
  const [isFaqOpen, setIsFaqOpen] = React.useState(false);
  const faqRef = React.useRef<HTMLDivElement>(null);

  // Dark Mode State - Default to true
  const [isDarkMode, setIsDarkMode] = React.useState<boolean>(() => {
    const saved = localStorage.getItem("aegismind-theme");
    if (saved) {
      return saved === "dark";
    }
    return true;
  });

  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("oauth")) {
      setActiveTab("connectors");
    }
  }, []);

  React.useEffect(() => {
    const root = document.documentElement;
    if (isDarkMode) {
      root.classList.add("dark");
      localStorage.setItem("aegismind-theme", "dark");
    } else {
      root.classList.remove("dark");
      localStorage.setItem("aegismind-theme", "light");
    }
  }, [isDarkMode]);

  const toggleTheme = () => setIsDarkMode((prev) => !prev);

  const handleBackToChat = React.useCallback(() => {
    setActiveTab("chat");
  }, []);

  // Keyboard shortcut to toggle docker menu (Cmd+B / Ctrl+B)
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setIsDockExpanded((prev) => !prev);
      }
      if (e.key === "Escape") {
        setIsDockExpanded(false);
        setIsFaqOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Close FAQ dropdown when clicking outside
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (faqRef.current && !faqRef.current.contains(event.target as Node)) {
        setIsFaqOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectTab = (tab: ActiveTab) => {
    setActiveTab(tab);
  };

  const filteredFaqs = React.useMemo(() => {
    const q = faqSearchQuery.trim().toLowerCase();
    if (!q) return FAQ_ITEMS;
    return FAQ_ITEMS.filter(
      (item) =>
        item.question.toLowerCase().includes(q) ||
        item.answer.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q)
    );
  }, [faqSearchQuery]);

  return (
    <div
      className={`relative min-h-screen h-screen w-full overflow-hidden font-sans flex flex-col transition-colors duration-200 ${
        isDarkMode ? "dark bg-[#0e111a] text-white" : "bg-[#f6f8fb] text-slate-900"
      }`}
    >
      {/* ── Background Video with Adaptive Theme Overlay ── */}
      <div className="bg fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <video
          className="bg-video absolute inset-0 w-full h-full object-cover pointer-events-none opacity-85"
          autoPlay
          muted
          loop
          playsInline
        >
          <source
            src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260809_012548_ef22562c-c0ae-4816-ad9d-f8922af4e6a7.mp4"
            type="video/mp4"
          />
        </video>
        <div
          className={`absolute inset-0 pointer-events-none transition-colors duration-200 ${
            isDarkMode
              ? "bg-gradient-to-b from-[#0e111a]/50 via-transparent to-[#0e111a]/70"
              : "bg-gradient-to-b from-white/70 via-white/40 to-white/80 backdrop-blur-[2px]"
          }`}
        />
      </div>

      {/* ─── Clear Header Section (All in One Place) ─── */}
      <header
        className={`sticky top-0 z-40 h-16 border-b transition-colors duration-200 shrink-0 shadow-sm ${
          isDarkMode
            ? "border-white/10 bg-[#121622]/80 backdrop-blur-xl text-white"
            : "border-slate-200/90 bg-white/90 backdrop-blur-xl text-slate-900"
        }`}
      >
        <div className="w-full px-4 sm:px-6 h-full flex items-center justify-between gap-2 sm:gap-4">
          {/* Left: Single Docker Toggle + Single AegisMind Logo (No duplicated navigation) */}
          <div className="flex items-center gap-2.5 sm:gap-3.5 shrink-0">
            {/* Single Docker Menu Toggle Button */}
            <button
              type="button"
              onClick={() => setIsDockExpanded((prev) => !prev)}
              aria-label="Toggle docker menu"
              className={`h-9.5 px-2.5 rounded-xl flex items-center gap-1.5 transition-all border shadow-xs ${
                isDockExpanded
                  ? "bg-primary text-white border-primary shadow-primary/20"
                  : isDarkMode
                  ? "text-white/70 hover:text-white bg-white/5 hover:bg-white/10 border-white/10"
                  : "text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 border-slate-200"
              }`}
              title="Toggle Feature Dock (Ctrl+B)"
            >
              <PanelLeft className="h-4.5 w-4.5" />
              <span className="text-xs font-semibold hidden sm:inline-block">Menu</span>
            </button>

            {/* Single Unified Project Brand Logo with Uploaded Logo Image */}
            <div
              onClick={() => setActiveTab("chat")}
              className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl select-none cursor-pointer transition-all hover:scale-[1.01] shrink-0 border border-cyan-500/30 dark:border-cyan-400/25 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-sm"
              title="AegisMind — Sovereign Second Brain"
            >
              <img
                src="/assets/aegismind-logo.jpg"
                alt="AegisMind Logo"
                className="h-8 w-8 rounded-lg object-cover shadow-sm border border-cyan-500/40 shrink-0"
              />
              <div className="flex flex-col justify-center leading-none pr-1">
                <div className="text-[17px] sm:text-[18px] font-black tracking-tight flex items-baseline">
                  <span className="text-slate-900 dark:text-white font-extrabold">Aegis</span>
                  <span className="font-extrabold text-cyan-500 dark:text-cyan-400 ml-0.5">Mind</span>
                </div>
                <div className="text-[8.5px] sm:text-[9px] font-bold tracking-[2.2px] uppercase mt-1 text-slate-700 dark:text-cyan-300/90 whitespace-nowrap">
                  SOVEREIGN SECOND BRAIN
                </div>
              </div>
            </div>

            {/* Back button if a feature other than chat is active */}
            {activeTab !== "chat" && (
              <button
                type="button"
                onClick={handleBackToChat}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-all ml-1"
                title="Return to Home Chat"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Back to Chat</span>
              </button>
            )}
          </div>

          {/* Center: Search Bar with Interactive Project FAQ & Instant Answers */}
          <div ref={faqRef} className="relative flex-1 max-w-md mx-2 sm:mx-4">
            <div
              onClick={() => setIsFaqOpen(true)}
              className={`flex items-center gap-2 h-9 px-3 rounded-xl border text-xs transition-all cursor-text ${
                isDarkMode
                  ? "bg-white/5 hover:bg-white/8 border-white/12 text-white/70 hover:border-white/25 focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/20"
                  : "bg-slate-100 hover:bg-slate-200/80 border-slate-200 text-slate-600 hover:border-slate-300 focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/20"
              }`}
            >
              <Search className="h-3.5 w-3.5 text-primary shrink-0" />
              <input
                type="text"
                placeholder="Ask or search usual questions about AegisMind..."
                value={faqSearchQuery}
                onFocus={() => setIsFaqOpen(true)}
                onChange={(e) => {
                  setFaqSearchQuery(e.target.value);
                  setIsFaqOpen(true);
                }}
                className="w-full bg-transparent outline-none placeholder:text-muted-foreground/60 text-xs"
              />
              <span className="hidden sm:inline-block px-1.5 py-0.5 rounded text-[10px] font-mono opacity-50 bg-black/10 dark:bg-white/10">
                FAQ
              </span>
            </div>

            {/* Instant Questions & Answers Popover Dropdown */}
            {isFaqOpen && (
              <div
                className={`absolute left-0 right-0 top-11 rounded-2xl border shadow-2xl p-3 z-50 animate-in fade-in-0 slide-in-from-top-2 duration-150 max-h-[460px] overflow-y-auto ${
                  isDarkMode
                    ? "bg-[#141826]/95 backdrop-blur-2xl border-white/15 text-white shadow-black/60"
                    : "bg-white/95 backdrop-blur-2xl border-slate-200 text-slate-900 shadow-slate-400/30"
                }`}
              >
                <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/10 dark:border-white/10">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-primary">
                    <Sparkles className="h-4 w-4" />
                    <span>Usual Questions & Instant Answers</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsFaqOpen(false)}
                    className="text-muted-foreground hover:text-foreground text-xs p-1 rounded hover:bg-white/10"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>

                <div className="space-y-2.5">
                  {filteredFaqs.length > 0 ? (
                    filteredFaqs.map((faq) => (
                      <div
                        key={faq.id}
                        className={`p-2.5 rounded-xl border transition-colors ${
                          isDarkMode
                            ? "bg-white/[0.03] hover:bg-white/[0.06] border-white/10"
                            : "bg-slate-50 hover:bg-slate-100 border-slate-200"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-1.5">
                            <HelpCircle className="h-3.5 w-3.5 text-primary shrink-0 mt-0.5" />
                            <h4 className="text-xs font-semibold leading-snug">
                              {faq.question}
                            </h4>
                          </div>
                          <span className="text-[10px] uppercase font-semibold tracking-wider px-1.5 py-0.5 rounded bg-primary/10 text-primary shrink-0">
                            {faq.category}
                          </span>
                        </div>
                        <p
                          className={`text-[11px] leading-relaxed mt-1.5 pl-5 ${
                            isDarkMode ? "text-white/70" : "text-slate-600"
                          }`}
                        >
                          {faq.answer}
                        </p>
                        <div className="mt-2 pl-5 flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setInitialChatQuery(faq.question);
                              setActiveTab("chat");
                              setIsFaqOpen(false);
                            }}
                            className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                          >
                            <span>Ask in AI Chat</span>
                            <ArrowLeft className="h-3 w-3 rotate-180" />
                          </button>
                          {faq.targetTab && (
                            <button
                              type="button"
                              onClick={() => {
                                selectTab(faq.targetTab!);
                                setIsFaqOpen(false);
                              }}
                              className="inline-flex items-center gap-1 text-[11px] font-medium text-muted-foreground hover:text-foreground"
                            >
                              <span>Open {TAB_LABELS[faq.targetTab]}</span>
                              <ExternalLink className="h-2.5 w-2.5" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="py-6 text-center text-xs text-muted-foreground">
                      No matching questions. Try another search or ask directly in AI Chat.
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Right Header: Brightness & Dark Mode Toggle (Visibly switches entire app) */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label="Toggle brightness and dark mode"
              className={`h-9 w-9 rounded-lg flex items-center justify-center transition-all border shadow-xs ${
                isDarkMode
                  ? "text-amber-400 bg-white/5 hover:bg-white/10 border-white/10 hover:border-white/20"
                  : "text-slate-800 bg-slate-100 hover:bg-slate-200 border-slate-200 hover:border-slate-300"
              }`}
              title={isDarkMode ? "Switch to Light Mode (Brightness)" : "Switch to Dark Mode"}
            >
              {isDarkMode ? (
                <Sun className="h-4.5 w-4.5 transition-transform hover:rotate-45" />
              ) : (
                <Moon className="h-4.5 w-4.5 transition-transform hover:-rotate-12" />
              )}
            </button>
          </div>
        </div>
      </header>

      {/* ─── Body Layout: Left Docker Menu + Main Content Canvas ─── */}
      <div className="relative z-10 flex-1 flex min-h-0 overflow-hidden">
        {/* ─── Left Docker Sidebar (Icons present, expands on click) ─── */}
        <aside
          className={`shrink-0 border-r flex flex-col transition-all duration-300 ease-in-out shadow-lg z-30 ${
            isDockExpanded ? "w-64 sm:w-72" : "w-14 sm:w-16"
          } ${
            isDarkMode
              ? "bg-[#141826]/90 backdrop-blur-2xl border-white/10 text-white"
              : "bg-white/95 backdrop-blur-2xl border-slate-200/90 text-slate-900"
          }`}
        >
          {/* Docker Header (Kept blank without Feature Dock text) */}
          {isDockExpanded && (
            <div
              className={`p-3 border-b flex items-center justify-between transition-colors ${
                isDarkMode ? "border-white/10" : "border-slate-200"
              }`}
            >
              <div />
              <button
                type="button"
                onClick={() => setIsDockExpanded(false)}
                className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
                title="Collapse Dock (Ctrl+B)"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          {/* Docker Items List */}
          <div className="flex-1 overflow-y-auto py-3 px-1.5 space-y-4">
            {SIDEBAR_SECTIONS.map((section) => (
              <div key={section.title} className="space-y-1">
                {isDockExpanded && (
                  <div className="px-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                    {section.title}
                  </div>
                )}
                <div className="space-y-1">
                  {section.items.map((item) => {
                    const Icon = item.icon;
                    const isActive = activeTab === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => selectTab(item.id)}
                        className={`w-full flex items-center rounded-xl transition-all group ${
                          isDockExpanded
                            ? "gap-3 px-3 py-2 text-left text-xs"
                            : "justify-center p-2.5"
                        } ${
                          isActive
                            ? "bg-primary/20 text-primary border border-primary/40 ring-1 ring-primary/20 font-semibold shadow-xs"
                            : isDarkMode
                            ? "text-white/70 hover:text-white hover:bg-white/8"
                            : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                        }`}
                        title={!isDockExpanded ? `${item.label}: ${item.description}` : undefined}
                      >
                        <Icon
                          className={`h-4.5 w-4.5 shrink-0 transition-colors ${
                            isActive
                              ? "text-primary"
                              : "text-muted-foreground group-hover:text-primary"
                          }`}
                        />
                        {isDockExpanded && (
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between">
                              <span className="truncate">{item.label}</span>
                              {isActive && (
                                <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                              )}
                            </div>
                            {item.description && (
                              <p className="text-[10px] truncate text-muted-foreground/80 mt-0.5">
                                {item.description}
                              </p>
                            )}
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </aside>

        {/* ─── Main Content Canvas (Fully Scrollable on All Features) ─── */}
        <main className="flex-1 min-h-0 flex flex-col overflow-y-auto">
          {/* Chat Feature View */}
          <div className={activeTab === "chat" ? "flex-1 flex flex-col min-h-0" : "hidden"}>
            <Chat
              currentTenantId={currentTenantId}
              currentUserId={currentUserId}
              initialQuery={initialChatQuery}
              onClearInitialQuery={() => setInitialChatQuery(undefined)}
            />
          </div>

          {/* Local Sources / Connectors Feature View (Smooth Scrolling Enabled) */}
          <div
            className={
              activeTab === "connectors"
                ? "flex-1 min-h-0 overflow-y-auto p-4 max-w-7xl mx-auto w-full"
                : "hidden"
            }
          >
            <Connectors />
          </div>

          {/* Datasets Feature View */}
          {activeTab === "datasets" && (
            <div className="flex-1 min-h-0 overflow-y-auto p-4 max-w-7xl mx-auto w-full">
              <Datasets
                currentTenantId={currentTenantId}
                currentUserId={currentUserId}
                onNavigateToChat={(query) => {
                  if (query) {
                    setInitialChatQuery(`What are the key points in ${query}?`);
                  }
                  setActiveTab("chat");
                }}
              />
            </div>
          )}

          {/* Notes Feature View */}
          {activeTab === "notes" && (
            <div className="flex-1 min-h-0 overflow-y-auto p-4 max-w-7xl mx-auto w-full">
              <Notes
                currentUserId={currentUserId}
                currentTenantId={currentTenantId}
                onNavigateToChat={(query) => {
                  if (query) {
                    setInitialChatQuery(query);
                  }
                  setActiveTab("chat");
                }}
              />
            </div>
          )}

          {/* Knowledge Graph Feature View */}
          {activeTab === "graph" && (
            <div className="flex-1 min-h-0 overflow-y-auto p-4 max-w-7xl mx-auto w-full">
              <KnowledgeGraph />
            </div>
          )}

          {/* Memory Recall Feature View */}
          {activeTab === "memory" && (
            <div className="flex-1 min-h-0 overflow-y-auto p-4 max-w-7xl mx-auto w-full">
              <Memory currentUserId={currentUserId} currentTenantId={currentTenantId} />
            </div>
          )}
        </main>
      </div>

      {/* ─── Footer Status Bar (Shows Project Name & Built by Team ZeroTrust) ─── */}
      <footer
        className={`relative z-10 border-t py-2 px-4 text-xs shrink-0 transition-colors ${
          isDarkMode
            ? "border-white/10 bg-[#121622]/90 text-white/70"
            : "border-slate-200 bg-white/95 text-slate-600 shadow-sm"
        }`}
      >
        <div className="max-w-7xl mx-auto flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="flex h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-medium text-muted-foreground">by ZeroTrust</span>
          </div>
          <span className="text-[11px] font-semibold text-foreground">AegisMind</span>
        </div>
      </footer>

      {/* Command Palette Modal */}
      <CommandPalette
        open={isCommandOpen}
        onOpenChange={setIsCommandOpen}
        onNavigate={(view) => {
          if (
            view === "chat" ||
            view === "connectors" ||
            view === "datasets" ||
            view === "notes" ||
            view === "graph" ||
            view === "memory"
          ) {
            setActiveTab(view);
          }
        }}
        onOpenResourcePicker={() => setIsResourcePickerOpen(true)}
      />

      {/* Resource Picker Ingest Modal */}
      <ResourcePicker
        open={isResourcePickerOpen}
        onOpenChange={setIsResourcePickerOpen}
      />
    </div>
  );
}
