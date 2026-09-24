import * as React from "react";
import { Chat } from "@/components/Chat";
import { Search } from "@/components/Search";
import { Connectors } from "@/components/Connectors";
import { Access } from "@/components/Access";
import { CommandPalette } from "@/components/CommandPalette";
import { ResourcePicker } from "@/components/ResourcePicker";
import { Button } from "@/components/ui/button";
import {
  Shield,
  MessageSquare,
  Search as SearchIcon,
  Share2,
  Network,
  FolderPlus,
  Command as CommandIcon,
  User,
  Building2,
} from "lucide-react";

type ActiveTab = "chat" | "search" | "connectors" | "access";

export function App() {
  const [activeTab, setActiveTab] = React.useState<ActiveTab>("chat");
  const [currentTenantId, setCurrentTenantId] = React.useState("corp-default");
  const [currentUserId, setCurrentUserId] = React.useState("alice");
  const [isCommandOpen, setIsCommandOpen] = React.useState(false);
  const [isResourcePickerOpen, setIsResourcePickerOpen] = React.useState(false);

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Global Navigation Header */}
      <header className="sticky top-0 z-40 border-b border-border/80 bg-background/95 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          {/* Logo & Platform Title */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-lg bg-primary/20 border border-primary/40 flex items-center justify-center text-primary font-bold shadow-xs">
                <Shield className="h-5 w-5" />
              </div>
              <div>
                <span className="font-bold text-sm tracking-tight text-foreground">
                  AegisMind
                </span>
                <span className="text-[10px] text-primary ml-1.5 font-semibold uppercase tracking-wider">
                  Lens
                </span>
              </div>
            </div>

            {/* Navigation Tabs */}
            <nav className="hidden md:flex items-center gap-1 ml-6 border-l border-border/60 pl-6 text-xs">
              <button
                type="button"
                onClick={() => setActiveTab("chat")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors ${
                  activeTab === "chat"
                    ? "bg-secondary text-foreground font-medium shadow-xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                <MessageSquare className="h-3.5 w-3.5 text-primary" />
                Chat
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("search")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors ${
                  activeTab === "search"
                    ? "bg-secondary text-foreground font-medium shadow-xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                <SearchIcon className="h-3.5 w-3.5 text-primary" />
                Search
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("connectors")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors ${
                  activeTab === "connectors"
                    ? "bg-secondary text-foreground font-medium shadow-xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                <Share2 className="h-3.5 w-3.5 text-primary" />
                Connectors
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("access")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors ${
                  activeTab === "access"
                    ? "bg-secondary text-foreground font-medium shadow-xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                <Network className="h-3.5 w-3.5 text-primary" />
                Access Graph
              </button>
            </nav>
          </div>

          {/* Right Header: Command Palette, Resource Picker & Active Context */}
          <div className="flex items-center gap-2">
            {/* Quick Ingest Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsResourcePickerOpen(true)}
              className="hidden sm:flex gap-1.5 text-xs h-8"
            >
              <FolderPlus className="h-3.5 w-3.5 text-emerald-400" />
              Ingest
            </Button>

            {/* Command Palette Trigger */}
            <button
              type="button"
              onClick={() => setIsCommandOpen(true)}
              className="flex items-center gap-2 rounded-lg border border-border/80 bg-muted/40 px-2.5 py-1 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors"
            >
              <CommandIcon className="h-3 w-3" />
              <span className="hidden sm:inline">Quick Jump...</span>
              <kbd className="hidden sm:inline rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono border border-border/40">
                ⌘K
              </kbd>
            </button>

            {/* Tenant & Identity Scope Switcher */}
            <div className="hidden lg:flex items-center gap-2 pl-2 border-l border-border/60 text-xs">
              <div className="flex items-center gap-1 text-muted-foreground">
                <Building2 className="h-3.5 w-3.5" />
                <select
                  value={currentTenantId}
                  onChange={(e) => setCurrentTenantId(e.target.value)}
                  className="bg-transparent text-xs font-mono text-foreground focus:outline-none cursor-pointer"
                >
                  <option value="corp-default" className="bg-card">corp-default</option>
                  <option value="tenant-finance" className="bg-card">tenant-finance</option>
                  <option value="tenant-external" className="bg-card">tenant-external</option>
                </select>
              </div>

              <div className="flex items-center gap-1 text-muted-foreground">
                <User className="h-3.5 w-3.5" />
                <select
                  value={currentUserId}
                  onChange={(e) => setCurrentUserId(e.target.value)}
                  className="bg-transparent text-xs font-mono text-primary font-medium focus:outline-none cursor-pointer"
                >
                  <option value="alice" className="bg-card">alice (eng)</option>
                  <option value="bob" className="bg-card">bob (contractor)</option>
                  <option value="charlie" className="bg-card">charlie (finance)</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1">
        {activeTab === "chat" && (
          <Chat currentTenantId={currentTenantId} currentUserId={currentUserId} />
        )}
        {activeTab === "search" && (
          <Search currentTenantId={currentTenantId} currentUserId={currentUserId} />
        )}
        {activeTab === "connectors" && <Connectors />}
        {activeTab === "access" && (
          <Access currentTenantId={currentTenantId} currentUserId={currentUserId} />
        )}
      </main>

      {/* Footer Status Bar */}
      <footer className="border-t border-border/60 bg-card/20 py-2 px-4 text-xs text-muted-foreground">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-1">
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-emerald-400" />
            <span>AegisMind Core v0.1.0</span>
            <span>•</span>
            <span>SpiceDB Zanzibar Engine Connected</span>
            <span>•</span>
            <span>Reciprocal Rank Fusion Active</span>
          </div>
          <div className="flex items-center gap-2 text-[11px]">
            <span>Zero Stale Read Guarantees</span>
            <span>•</span>
            <span className="text-emerald-400 font-mono">Rule 5 Compliant</span>
          </div>
        </div>
      </footer>

      {/* Command Palette Modal */}
      <CommandPalette
        open={isCommandOpen}
        onOpenChange={setIsCommandOpen}
        onNavigate={(view) => setActiveTab(view)}
        onOpenResourcePicker={() => setIsResourcePickerOpen(true)}
      />

      {/* Resource Picker Modal */}
      <ResourcePicker
        open={isResourcePickerOpen}
        onOpenChange={setIsResourcePickerOpen}
      />
    </div>
  );
}
