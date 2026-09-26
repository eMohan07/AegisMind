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
import { listNotes, getNoteDetail, type NoteSummary, type NoteDetail } from "@/lib/api";
import {
  FileText,
  Tag,
  Calendar,
  Search,
  RefreshCw,
  Sparkles,
  BookOpen,
  Terminal,
} from "lucide-react";

export function Notes() {
  const [notes, setNotes] = React.useState<NoteSummary[]>([]);
  const [selectedSlug, setSelectedSlug] = React.useState<string | null>(null);
  const [selectedNote, setSelectedNote] = React.useState<NoteDetail | null>(null);
  const [selectedTag, setSelectedTag] = React.useState<string | null>(null);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = React.useState(false);

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

  // Aggregate all unique tags
  const allTags = React.useMemo(() => {
    const tagSet = new Set<string>();
    notes.forEach((n) => n.tags.forEach((t) => tagSet.add(t)));
    return Array.from(tagSet);
  }, [notes]);

  // Filter notes by search query
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

  return (
    <div className="flex-1 p-6 max-w-7xl mx-auto w-full space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/70 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
              <BookOpen className="h-6 w-6 text-primary" />
              Sovereign Notes
            </h1>
            <Badge variant="outline" className="border-primary/40 text-primary text-xs">
              Local Vault
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Personal markdown knowledge base created and maintained offline by the local agent.
          </p>
        </div>
        <div className="flex items-center gap-2">
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
      </div>

      {/* Main 2-Column Layout */}
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
                  Ask the Sovereign Agent to diagnose a problem and save a note.
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
                    <Badge variant="outline" className="text-[10px] border-border text-muted-foreground">
                      {selectedNote.slug}
                    </Badge>
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
  );
}
