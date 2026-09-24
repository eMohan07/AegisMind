import * as React from "react";
import { Command } from "cmdk";
import {
  Search,
  MessageSquare,
  Network,
  Share2,
  FolderPlus,
  ShieldCheck,
  Laptop,
} from "lucide-react";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigate: (view: "chat" | "search" | "connectors" | "access") => void;
  onOpenResourcePicker: () => void;
}

export function CommandPalette({
  open,
  onOpenChange,
  onNavigate,
  onOpenResourcePicker,
}: CommandPaletteProps) {
  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
    };

    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/70 backdrop-blur-sm animate-in fade-in-0">
      <div className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
        <Command
          className="w-full"
          onKeyDown={(e: React.KeyboardEvent) => {
            if (e.key === "Escape") {
              onOpenChange(false);
            }
          }}
        >
          <div className="flex items-center border-b border-border px-3">
            <Search className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
            <Command.Input
              autoFocus
              placeholder="Type a command or search documents..."
              className="flex h-12 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
          <Command.List className="max-h-72 overflow-y-auto p-2 text-sm text-foreground">
            <Command.Empty className="p-4 text-center text-sm text-muted-foreground">
              No results found.
            </Command.Empty>

            <Command.Group heading="Navigation" className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
              <Command.Item
                onSelect={() => {
                  onNavigate("chat");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-accent hover:text-accent-foreground aria-selected:bg-accent aria-selected:text-accent-foreground"
              >
                <MessageSquare className="h-4 w-4 text-primary" />
                <span>Conversational Chat</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onNavigate("search");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-accent hover:text-accent-foreground aria-selected:bg-accent aria-selected:text-accent-foreground"
              >
                <Search className="h-4 w-4 text-primary" />
                <span>Instant Hybrid Search</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onNavigate("connectors");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-accent hover:text-accent-foreground aria-selected:bg-accent aria-selected:text-accent-foreground"
              >
                <Share2 className="h-4 w-4 text-primary" />
                <span>Enterprise Connectors</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onNavigate("access");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-accent hover:text-accent-foreground aria-selected:bg-accent aria-selected:text-accent-foreground"
              >
                <Network className="h-4 w-4 text-primary" />
                <span>Zanzibar Access Graph</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Actions" className="px-2 py-1.5 text-xs font-semibold text-muted-foreground mt-2">
              <Command.Item
                onSelect={() => {
                  onOpenChange(false);
                  onOpenResourcePicker();
                }}
                className="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-accent hover:text-accent-foreground aria-selected:bg-accent aria-selected:text-accent-foreground"
              >
                <FolderPlus className="h-4 w-4 text-emerald-400" />
                <span>Select Resources to Ingest...</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onNavigate("access");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-accent hover:text-accent-foreground aria-selected:bg-accent aria-selected:text-accent-foreground"
              >
                <ShieldCheck className="h-4 w-4 text-indigo-400" />
                <span>Inspect Permission Revocations</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  window.open("https://github.com/eMohan07/AegisMind", "_blank");
                  onOpenChange(false);
                }}
                className="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-accent hover:text-accent-foreground aria-selected:bg-accent aria-selected:text-accent-foreground"
              >
                <Laptop className="h-4 w-4 text-muted-foreground" />
                <span>Open Documentation</span>
              </Command.Item>
            </Command.Group>
          </Command.List>
          <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-muted-foreground">
            <span>Navigation shortcut</span>
            <kbd className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono">ESC to close</kbd>
          </div>
        </Command>
      </div>
    </div>
  );
}
