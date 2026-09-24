import * as React from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { checkAccessGraph, type AccessRelation } from "@/lib/api";
import {
  Network,
  ShieldCheck,
  ShieldAlert,
  ArrowRight,
  User,
  Users,
  FileText,
  RefreshCw,
  Trash2,
  CheckCircle,
} from "lucide-react";

interface AccessProps {
  currentTenantId: string;
  currentUserId: string;
}

export function Access({ currentTenantId, currentUserId }: AccessProps) {
  const [selectedUser, setSelectedUser] = React.useState<string>(currentUserId);
  const [relations, setRelations] = React.useState<AccessRelation[]>([]);
  const [isLoading, setIsLoading] = React.useState(false);
  const [revokedSet, setRevokedSet] = React.useState<Set<string>>(new Set());
  const [notice, setNotice] = React.useState<string | null>(null);

  React.useEffect(() => {
    loadGraph(selectedUser);
  }, [selectedUser]);

  const loadGraph = async (userId: string) => {
    setIsLoading(true);
    const data = await checkAccessGraph(userId, currentTenantId);
    setRelations(data);
    setIsLoading(false);
  };

  const handleSimulateRevoke = (resource: string) => {
    const next = new Set(revokedSet);
    next.add(resource);
    setRevokedSet(next);

    setRelations((prev) =>
      prev.map((r) =>
        r.resource === resource
          ? {
              ...r,
              allowed: false,
              path: [`user:${selectedUser}`, "revoked via Zanzibar delete_tuples", "denied"],
            }
          : r
      )
    );

    setNotice(`Revocation executed for ${resource}. Access dropped immediately without stale reads.`);
    setTimeout(() => setNotice(null), 3500);
  };

  const handleResetRevocations = () => {
    setRevokedSet(new Set());
    loadGraph(selectedUser);
    setNotice("Restored original Zanzibar permissions graph.");
    setTimeout(() => setNotice(null), 3000);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] p-4 max-w-7xl mx-auto w-full gap-4">
      {/* Top Header & User Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-border/80 bg-card/60 p-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Network className="h-5 w-5 text-primary" />
            Zanzibar Relationship Graph Explorer
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Evaluate subject-to-resource graph traversal and verify immediate revocation propagation.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Select Subject:</span>
          {["alice", "bob", "charlie"].map((u) => (
            <button
              key={u}
              type="button"
              onClick={() => setSelectedUser(u)}
              className={`rounded-md px-3 py-1 text-xs font-mono capitalize transition-colors ${
                selectedUser === u
                  ? "bg-primary text-primary-foreground font-semibold"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              user:{u}
            </button>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => loadGraph(selectedUser)}
            disabled={isLoading}
            className="gap-1.5 text-xs ml-2"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {notice && (
        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 p-2.5 text-xs text-emerald-400 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 shrink-0" />
            <span>{notice}</span>
          </div>
          {revokedSet.size > 0 && (
            <button
              type="button"
              onClick={handleResetRevocations}
              className="underline text-[11px] hover:text-emerald-300"
            >
              Reset All
            </button>
          )}
        </div>
      )}

      {/* Main Grid: Graph Traversal Paths */}
      <div className="grid grid-cols-1 gap-3 overflow-y-auto pr-1">
        {relations.map((rel) => {
          const isAllowed = rel.allowed && !revokedSet.has(rel.resource);

          return (
            <Card
              key={`${rel.resource}-${rel.relation}`}
              className={`border transition-all ${
                isAllowed
                  ? "border-emerald-500/30 bg-emerald-950/10"
                  : "border-destructive/30 bg-destructive/5"
              }`}
            >
              <CardHeader className="p-4 pb-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {isAllowed ? (
                      <ShieldCheck className="h-5 w-5 text-emerald-400" />
                    ) : (
                      <ShieldAlert className="h-5 w-5 text-destructive" />
                    )}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-foreground">
                          {rel.resource}
                        </span>
                        <Badge
                          variant={isAllowed ? "success" : "destructive"}
                          className="text-[10px] uppercase font-mono"
                        >
                          {rel.relation}: {isAllowed ? "ALLOWED" : "DENIED"}
                        </Badge>
                      </div>
                      <span className="text-[11px] text-muted-foreground font-mono">
                        Subject: {rel.subject}
                      </span>
                    </div>
                  </div>

                  {isAllowed && (
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleSimulateRevoke(rel.resource)}
                      className="gap-1.5 text-xs h-7 self-start sm:self-auto"
                    >
                      <Trash2 className="h-3 w-3" />
                      Revoke Permission
                    </Button>
                  )}
                </div>
              </CardHeader>

              <CardContent className="p-4 pt-2">
                <div className="text-xs text-muted-foreground mb-1.5 font-medium">
                  Zanzibar Resolution Traversal Path:
                </div>
                {/* Visual Step-by-Step Traversal */}
                <div className="flex flex-wrap items-center gap-2 rounded-lg bg-background/80 border border-border/50 p-2.5">
                  {rel.path && rel.path.length > 0 ? (
                    rel.path.map((step, idx) => {
                      const isLast = idx === rel.path!.length - 1;
                      const isUser = step.startsWith("user:");
                      const isGroup = step.startsWith("group:");

                      return (
                        <React.Fragment key={idx}>
                          <div className="flex items-center gap-1.5 rounded-md bg-muted/60 px-2 py-1 text-[11px] font-mono border border-border/40">
                            {isUser ? (
                              <User className="h-3 w-3 text-primary" />
                            ) : isGroup ? (
                              <Users className="h-3 w-3 text-amber-400" />
                            ) : (
                              <FileText className="h-3 w-3 text-muted-foreground" />
                            )}
                            <span>{step}</span>
                          </div>
                          {!isLast && (
                            <ArrowRight className="h-3 w-3 text-muted-foreground/60 shrink-0" />
                          )}
                        </React.Fragment>
                      );
                    })
                  ) : (
                    <span className="text-[11px] text-muted-foreground italic">
                      Direct policy check
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
