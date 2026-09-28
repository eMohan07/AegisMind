import * as React from "react";
import { Command } from "cmdk";
import {
  MessageSquare,
  Share2,
  FolderPlus,
  Laptop,
  Database,
  BookOpen,
  GitBranch,
  Brain,
  Terminal,
  Search,
} from "lucide-react";

export type NavView =
  | "chat"
  | "connectors"
  | "datasets"
  | "notes"
  | "graph"
  | "memory";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigate: (view: NavView) => void;
  onOpenResourcePicker: () => void;
}

export function CommandPalette({
  open,
  onOpenChange,
  onNavigate,
  onOpenResourcePicker,
}: CommandPaletteProps) {
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Toggle on Cmd+K / Ctrl+K
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
      // Close immediately on Escape
      if (e.key === "Escape" && open) {
        e.preventDefault();
        onOpenChange(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div
      onClick={() => onOpenChange(false)}
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/60 backdrop-blur-sm animate-in fade-in-0 px-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl overflow-hidden rounded-xl border border-white/15 bg-[#10131c] shadow-2xl text-white"
      >
        <Command
          className="w-full"
          onKeyDown={(e: React.KeyboardEvent) => {
            if (e.key === "Escape") {
              e.preventDefault();
              onOpenChange(false);
            }
          }}
        >
          <div className="flex items-center border-b border-white/10 px-3">
            <Search className="mr-2 h-4 w-4 shrink-0 text-white/50" />
            <Command.Input
              autoFocus
              placeholder="Type a command or search tools, docs & views..."
              className="flex h-12 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-white/40 disabled:cursor-not-allowed disabled:opacity-50 text-white"
            />
          </div>
          <Command.List className="max-h-80 overflow-y-auto p-2 text-sm text-white">
            <Command.Empty className="p-4 text-center text-sm text-white/50">
              No results found.
            </Command.Empty>

            <Command.Group heading="Navigation" className="px-2 py-1.5 text-xs font-semibold text-white/50">
              <Command.Item
                onSelect={() => {
                  onNavigate("chat");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2.5 rounded-md px-2.5 py-2 text-sm hover:bg-white/10 aria-selected:bg-white/10 transition-colors"
              >
                <MessageSquare className="h-4 w-4 text-primary" />
                <span>Conversational AI Chat</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onNavigate("connectors");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2.5 rounded-md px-2.5 py-2 text-sm hover:bg-white/10 aria-selected:bg-white/10 transition-colors"
              >
                <Share2 className="h-4 w-4 text-primary" />
                <span>Enterprise Connectors</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onNavigate("datasets");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2.5 rounded-md px-2.5 py-2 text-sm hover:bg-white/10 aria-selected:bg-white/10 transition-colors"
              >
                <Database className="h-4 w-4 text-primary" />
                <span>Datasets & Study Hub</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onNavigate("notes");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2.5 rounded-md px-2.5 py-2 text-sm hover:bg-white/10 aria-selected:bg-white/10 transition-colors"
              >
                <BookOpen className="h-4 w-4 text-primary" />
                <span>Notes & Canvas</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onNavigate("graph");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2.5 rounded-md px-2.5 py-2 text-sm hover:bg-white/10 aria-selected:bg-white/10 transition-colors"
              >
                <GitBranch className="h-4 w-4 text-primary" />
                <span>Knowledge Graph</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onNavigate("memory");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2.5 rounded-md px-2.5 py-2 text-sm hover:bg-white/10 aria-selected:bg-white/10 transition-colors"
              >
                <Brain className="h-4 w-4 text-primary" />
                <span>Long-Term Memory</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Actions" className="px-2 py-1.5 text-xs font-semibold text-white/50 mt-2 border-t border-white/10 pt-2">
              <Command.Item
                onSelect={() => {
                  onOpenChange(false);
                  onOpenResourcePicker();
                }}
                className="flex cursor-pointer select-none items-center gap-2.5 rounded-md px-2.5 py-2 text-sm hover:bg-white/10 aria-selected:bg-white/10 transition-colors"
              >
                <FolderPlus className="h-4 w-4 text-emerald-400" />
                <span>Ingest Documents & Data Sources...</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  window.open("https://github.com/eMohan07/AegisMind", "_blank");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2.5 rounded-md px-2.5 py-2 text-sm hover:bg-white/10 aria-selected:bg-white/10 transition-colors"
              >
                <Laptop className="h-4 w-4 text-white/50" />
                <span>Open Documentation</span>
              </Command.Item>
            </Command.Group>
          </Command.List>
          <div className="flex items-center justify-between border-t border-white/10 px-3 py-2 text-xs text-white/50 bg-black/40">
            <span>Navigate with ↑↓, Enter to select</span>
            <kbd className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-mono border border-white/15">ESC to close</kbd>
          </div>
        </Command>
      </div>
    </div>
  );
}
