import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Search,
  Folder,
  FileText,
  Hash,
  CheckCircle2,
  FolderTree,
  Building,
  HardDrive,
  RefreshCw,
} from "lucide-react";

interface ResourceItem {
  id: string;
  source: "google_drive" | "confluence" | "slack" | "sharepoint";
  type: "folder" | "file" | "channel" | "space";
  name: string;
  path: string;
  size?: string;
  updatedAt: string;
}

const SAMPLE_RESOURCES: ResourceItem[] = [
  {
    id: "gdrive-fld-1",
    source: "google_drive",
    type: "folder",
    name: "Engineering Architecture Docs",
    path: "/Shared Drives/Engineering/Architecture",
    updatedAt: "2 hours ago",
  },
  {
    id: "gdrive-doc-101",
    source: "google_drive",
    type: "file",
    name: "Zero Trust Security Specification v2.pdf",
    path: "/Shared Drives/Engineering/Architecture/Zero Trust Security Specification v2.pdf",
    size: "2.4 MB",
    updatedAt: "Today, 11:30 AM",
  },
  {
    id: "conf-spc-eng",
    source: "confluence",
    type: "space",
    name: "Core Infrastructure Wiki",
    path: "INFRA: Core Infrastructure",
    updatedAt: "Yesterday",
  },
  {
    id: "conf-doc-304",
    source: "confluence",
    type: "file",
    name: "Zanzibar SpiceDB Deployment Guide",
    path: "INFRA / Guides / Zanzibar SpiceDB Deployment Guide",
    size: "180 KB",
    updatedAt: "3 days ago",
  },
  {
    id: "slack-chn-dev",
    source: "slack",
    type: "channel",
    name: "dev-security-alerts",
    path: "#dev-security-alerts (Private)",
    updatedAt: "10 mins ago",
  },
  {
    id: "slack-chn-gen",
    source: "slack",
    type: "channel",
    name: "announcements",
    path: "#announcements (Public)",
    updatedAt: "1 hour ago",
  },
  {
    id: "sp-lib-legal",
    source: "sharepoint",
    type: "folder",
    name: "Compliance & Audit Documents",
    path: "Compliance Team Site / Documents / 2026",
    size: "14.2 MB",
    updatedAt: "Aug 12, 2026",
  },
];

interface ResourcePickerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirmSelection?: (selectedIds: string[]) => void;
}

export function ResourcePicker({
  open,
  onOpenChange,
  onConfirmSelection,
}: ResourcePickerProps) {
  const [searchQuery, setSearchQuery] = React.useState("");
  const [selectedSource, setSelectedSource] = React.useState<string>("all");
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [statusMessage, setStatusMessage] = React.useState<string | null>(null);

  const filteredResources = SAMPLE_RESOURCES.filter((item) => {
    const matchesSource =
      selectedSource === "all" || item.source === selectedSource;
    const matchesSearch =
      item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.path.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSource && matchesSearch;
  });

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedIds(next);
  };

  const selectAll = () => {
    const allFiltered = new Set(filteredResources.map((r) => r.id));
    setSelectedIds(allFiltered);
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
  };

  const handleIngest = async () => {
    setIsSubmitting(true);
    setStatusMessage(null);

    // Simulate scheduling ingestion workflow via Scribe worker
    setTimeout(() => {
      setIsSubmitting(false);
      setStatusMessage(`Ingestion pipeline dispatched for ${selectedIds.size} resources.`);
      if (onConfirmSelection) {
        onConfirmSelection(Array.from(selectedIds));
      }
      setTimeout(() => {
        setStatusMessage(null);
        onOpenChange(false);
      }, 1200);
    }, 800);
  };

  const getSourceIcon = (source: ResourceItem["source"]) => {
    switch (source) {
      case "google_drive":
        return <HardDrive className="h-4 w-4 text-emerald-400" />;
      case "confluence":
        return <FolderTree className="h-4 w-4 text-blue-400" />;
      case "slack":
        return <Hash className="h-4 w-4 text-pink-400" />;
      case "sharepoint":
        return <Building className="h-4 w-4 text-cyan-400" />;
    }
  };

  const getTypeIcon = (type: ResourceItem["type"]) => {
    switch (type) {
      case "folder":
      case "space":
        return <Folder className="h-4 w-4 text-amber-400" />;
      case "channel":
        return <Hash className="h-4 w-4 text-muted-foreground" />;
      case "file":
      default:
        return <FileText className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderTree className="h-5 w-5 text-primary" />
            Select Resources to Ingest
          </DialogTitle>
          <DialogDescription>
            Choose specific workspaces, folders, spaces, or channels for access controlled indexing.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Search and Source filters */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center justify-between">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Filter resources by name or path..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            <div className="flex items-center gap-1 overflow-x-auto text-xs">
              {["all", "google_drive", "confluence", "slack", "sharepoint"].map((src) => (
                <button
                  key={src}
                  type="button"
                  onClick={() => setSelectedSource(src)}
                  className={`rounded-md px-2.5 py-1 text-xs capitalize transition-colors ${
                    selectedSource === src
                      ? "bg-primary text-primary-foreground font-medium"
                      : "bg-muted text-muted-foreground hover:bg-muted/80"
                  }`}
                >
                  {src.replace("_", " ")}
                </button>
              ))}
            </div>
          </div>

          {/* Quick selection stats */}
          <div className="flex items-center justify-between text-xs text-muted-foreground border-b border-border/50 pb-2">
            <span>
              {selectedIds.size} of {filteredResources.length} items selected
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={selectAll}
                className="hover:text-primary transition-colors"
              >
                Select Visible
              </button>
              <span>•</span>
              <button
                type="button"
                onClick={clearSelection}
                className="hover:text-primary transition-colors"
              >
                Clear
              </button>
            </div>
          </div>

          {/* Resource List */}
          <div className="max-h-72 overflow-y-auto space-y-1.5 pr-1">
            {filteredResources.length === 0 ? (
              <div className="p-8 text-center text-sm text-muted-foreground">
                No matching resources found.
              </div>
            ) : (
              filteredResources.map((item) => {
                const isSelected = selectedIds.has(item.id);
                return (
                  <div
                    key={item.id}
                    onClick={() => toggleSelect(item.id)}
                    className={`flex cursor-pointer items-center justify-between rounded-lg border p-2.5 text-sm transition-all ${
                      isSelected
                        ? "border-primary bg-primary/10 text-foreground"
                        : "border-border/60 bg-card/60 hover:bg-muted/50"
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border ${
                          isSelected
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-muted-foreground/40 bg-transparent"
                        }`}
                      >
                        {isSelected && <CheckCircle2 className="h-3.5 w-3.5" />}
                      </div>
                      <div className="flex items-center gap-2 min-w-0">
                        {getTypeIcon(item.type)}
                        <div className="truncate">
                          <p className="font-medium text-xs leading-none truncate">
                            {item.name}
                          </p>
                          <p className="text-[11px] text-muted-foreground truncate mt-1">
                            {item.path}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      <Badge variant="outline" className="text-[10px] gap-1 px-1.5 py-0">
                        {getSourceIcon(item.source)}
                        <span className="capitalize">{item.source.replace("_", " ")}</span>
                      </Badge>
                      {item.size && (
                        <span className="text-[10px] text-muted-foreground hidden sm:inline">
                          {item.size}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {statusMessage && (
            <div className="rounded-md bg-emerald-500/10 border border-emerald-500/30 p-2.5 text-xs text-emerald-400 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              <span>{statusMessage}</span>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            onClick={handleIngest}
            disabled={selectedIds.size === 0 || isSubmitting}
            className="gap-2"
          >
            {isSubmitting ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                Dispatching Sync...
              </>
            ) : (
              `Ingest Selected (${selectedIds.size})`
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
