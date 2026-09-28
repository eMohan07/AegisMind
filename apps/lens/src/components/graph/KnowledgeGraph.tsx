import * as React from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Network,
  Shield,
  Search,
  Database,
  Cpu,
  CheckCircle2,
  Layers,
  Sliders,
  Sparkles,
  ArrowRight,
  Info,
  Zap,
  Lock,
  RotateCcw,
} from "lucide-react";

export interface RagNode {
  id: string;
  name: string;
  subtitle: string;
  stageNumber: string;
  stageBadge: string;
  category: "input" | "retrieval" | "security" | "synthesis";
  color: string;
  tech: string;
  description: string;
  ragRole: string;
  latency: string;
  securityGuarantee: string;
  inputs: string;
  outputs: string;
  x: number;
  y: number;
  width: number;
  height: number;
  iconName: "search" | "network" | "layers" | "shield" | "sliders" | "cpu" | "check";
}

// 7 Cleanly sequenced nodes from Left (User Input) to Right (AI Output)
const RAG_PIPELINE_NODES: RagNode[] = [
  {
    id: "rag-input",
    name: "User Input",
    subtitle: "Prompt & Intent",
    stageNumber: "01",
    stageBadge: "Stage 1: Input",
    category: "input",
    color: "#06b6d4", // cyan
    tech: "Regex Token Sanitizer & Intent Parser",
    description: "Captures natural language query from chatbox, strips potential prompt injection attacks, and prepares query vector.",
    ragRole: "Initiates RAG retrieval dispatch and generates temporal and author filters.",
    latency: "< 2 ms",
    securityGuarantee: "Input sanitized in local memory; shell characters and prompt injections neutralized.",
    inputs: "User prompt from chat interface",
    outputs: "Sanitized query text & query embedding vector",
    x: 40,
    y: 95,
    width: 130,
    height: 165,
    iconName: "search",
  },
  {
    id: "rag-ontology",
    name: "Entity Expansion",
    subtitle: "Knowledge Graph",
    stageNumber: "02",
    stageBadge: "Stage 2: Expansion",
    category: "retrieval",
    color: "#a855f7", // purple
    tech: "Entity-Relation Graph Index",
    description: "Traverses linked conceptual nodes (entities, projects, systems) to expand query semantics.",
    ragRole: "Supplements raw query with connected entity keywords to avoid missing vocabulary mismatches.",
    latency: "4.2 ms",
    securityGuarantee: "Node visibility respects user role; unpermitted entities are pruned prior to expansion.",
    inputs: "Sanitized query tokens",
    outputs: "Expanded entity list & synonym graph nodes",
    x: 215,
    y: 95,
    width: 130,
    height: 165,
    iconName: "network",
  },
  {
    id: "rag-hybrid",
    name: "Hybrid Search",
    subtitle: "Qdrant Vector DB",
    stageNumber: "03",
    stageBadge: "Stage 3: Retrieval",
    category: "retrieval",
    color: "#0ea5e9", // sky
    tech: "Dense HNSW (MiniLM) + Sparse BM25",
    description: "Runs dense vector cosine similarity and sparse BM25 keyword matching concurrently, fusing scores with Reciprocal Rank Fusion (RRF).",
    ragRole: "Guarantees high recall across both conceptual meaning and exact term numbers/acronyms.",
    latency: "11.8 ms",
    securityGuarantee: "Purely local in-process retrieval; zero network telemetry or cloud API calls.",
    inputs: "Query vector + expanded entity tokens",
    outputs: "Top-20 candidate chunk indices with fused RRF scores",
    x: 390,
    y: 95,
    width: 130,
    height: 165,
    iconName: "layers",
  },
  {
    id: "rag-guard",
    name: "Zanzibar ACL",
    subtitle: "Zero-Trust Gate",
    stageNumber: "04",
    stageBadge: "Stage 4: Security",
    category: "security",
    color: "#f59e0b", // amber
    tech: "Cryptographic Zanzibar Token Gate",
    description: "Evaluates cryptographic user tokens against tenant, document permissions, and role-based policies in real time.",
    ragRole: "Zero Stale Reads guarantee: unauthorized chunks are dropped BEFORE reaching the LLM context window.",
    latency: "2.8 ms",
    securityGuarantee: "Guaranteed zero data leakage. Revoked documents immediately disappear from retrieval.",
    inputs: "Candidate chunks + user session token",
    outputs: "Authorized chunks only (unauthorized chunks discarded)",
    x: 565,
    y: 95,
    width: 130,
    height: 165,
    iconName: "shield",
  },
  {
    id: "rag-reranker",
    name: "Cross-Encoder",
    subtitle: "Deep Reranking",
    stageNumber: "05",
    stageBadge: "Stage 5: Rerank",
    category: "retrieval",
    color: "#3b82f6", // blue
    tech: "BAAI/BGE-Reranker-Large (Local FP16)",
    description: "Computes full bidirectional cross-attention across [Query, Document] pairs to compute exact relevance scores.",
    ragRole: "Eliminates retrieval noise, selecting only the top 3-5 authoritative chunks for prompt synthesis.",
    latency: "17.4 ms",
    securityGuarantee: "Runs entirely on local compute; zero cloud egress.",
    inputs: "Authorized candidate chunks",
    outputs: "Top-5 high-confidence snippets with relevance scores",
    x: 740,
    y: 95,
    width: 130,
    height: 165,
    iconName: "sliders",
  },
  {
    id: "rag-ollama",
    name: "Local LLM",
    subtitle: "Ollama LLaMA 3.2",
    stageNumber: "06",
    stageBadge: "Stage 6: Synthesis",
    category: "synthesis",
    color: "#8b5cf6", // violet
    tech: "Ollama Offline 3B Runtime",
    description: "Locally running open-weight large language model. Synthesizes responses strictly grounded in supplied context.",
    ragRole: "Generates fluent, intelligent answers bounded by the verified chunks to prevent hallucinations.",
    latency: "165 ms TTFT",
    securityGuarantee: "100% Air-Gapped. No external network connections, telemetry, or third-party cloud APIs.",
    inputs: "Strict prompt template + Reranked chunks + Memory",
    outputs: "Streaming synthesized answer tokens",
    x: 915,
    y: 95,
    width: 130,
    height: 165,
    iconName: "cpu",
  },
  {
    id: "rag-output",
    name: "AI Output",
    subtitle: "Verified Citations",
    stageNumber: "07",
    stageBadge: "Stage 7: Output",
    category: "synthesis",
    color: "#10b981", // emerald
    tech: "Cryptographic Provenance Stream",
    description: "Presents real-time streaming answer with clickable citation badges showing exact document IDs and snippets.",
    ragRole: "User receives verifiable answer with 100% auditability and zero hallucination risk.",
    latency: "Live SSE Stream",
    securityGuarantee: "Every claim backed by a verified document chunk with cryptographic token proof.",
    inputs: "Synthesized token stream + Citation metadata",
    outputs: "Rendered response with verified citation badges",
    x: 1090,
    y: 95,
    width: 130,
    height: 165,
    iconName: "check",
  },
];

export function KnowledgeGraph() {
  const [selectedNode, setSelectedNode] = React.useState<RagNode>(RAG_PIPELINE_NODES[0]);


  const renderIcon = (name: RagNode["iconName"], color: string) => {
    const props = { className: "h-4 w-4", style: { color } };
    switch (name) {
      case "search":
        return <Search {...props} />;
      case "network":
        return <Network {...props} />;
      case "layers":
        return <Layers {...props} />;
      case "shield":
        return <Shield {...props} />;
      case "sliders":
        return <Sliders {...props} />;
      case "cpu":
        return <Cpu {...props} />;
      case "check":
        return <CheckCircle2 {...props} />;
      default:
        return <Sparkles {...props} />;
    }
  };

  return (
    <div className="w-full space-y-5 pb-8 animate-in fade-in-50 duration-200">
      {/* ─── Top Header Card ─── */}
      <div className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl p-4 sm:p-5 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 shrink-0">
            <Network className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold tracking-tight text-foreground">
                AegisMind Sovereign RAG Architecture
              </h1>
              <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px] font-mono flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Live Continuous Flow
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Left (User Input) ➔ In-between (Vector DB, Zanzibar ACL, Rerank) ➔ Right (AI Output). Fitted inside container with single moving arrow.
            </p>
          </div>
        </div>

        {/* Reset / Inspect button */}
        <div className="flex items-center gap-2 self-start md:self-auto">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSelectedNode(RAG_PIPELINE_NODES[0])}
            className="h-8 px-2.5 text-xs text-muted-foreground hover:text-foreground"
            title="Inspect first stage"
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1" />
            <span>Reset View</span>
          </Button>
        </div>
      </div>

      {/* ─── Architectural Metrics Stats Row ─── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="rounded-xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-md p-3">
          <div className="text-lg font-black text-cyan-400">100% Air-Gapped</div>
          <div className="text-[11px] text-muted-foreground mt-0.5 font-medium">0 Cloud Egress</div>
        </Card>
        <Card className="rounded-xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-md p-3">
          <div className="text-lg font-black text-amber-400">Zero Stale Reads</div>
          <div className="text-[11px] text-muted-foreground mt-0.5 font-medium">Zanzibar ACL Gate Active</div>
        </Card>
        <Card className="rounded-xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-md p-3">
          <div className="text-lg font-black text-sky-400">&lt; 45ms P95</div>
          <div className="text-[11px] text-muted-foreground mt-0.5 font-medium">Local Retrieval Latency</div>
        </Card>
        <Card className="rounded-xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-md p-3">
          <div className="text-lg font-black text-emerald-400">Verifiable Citations</div>
          <div className="text-[11px] text-muted-foreground mt-0.5 font-medium">Exact Document Proof</div>
        </Card>
      </div>

      {/* ─── Main Pipeline Box (Clean Padding, Fitted Inside Box, Single Moving Arrow) ─── */}
      <div className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-xl overflow-hidden p-4 sm:p-6 relative">
        {/* Stage Zone Headers Across the Top */}
        <div className="grid grid-cols-12 gap-2 text-center pb-3 border-b border-border/40 text-[11px] font-bold uppercase tracking-wider">
          <div className="col-span-2 text-cyan-400 flex items-center justify-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
            User Input
          </div>
          <div className="col-span-8 text-sky-400 flex items-center justify-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
            In-Between Retrieval & Security Process (Stages 2 – 6)
            <ArrowRight className="h-3 w-3 inline text-muted-foreground/60" />
          </div>
          <div className="col-span-2 text-emerald-400 flex items-center justify-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            AI Output
          </div>
        </div>

        {/* SVG Pipeline Canvas with generous cell padding & exactly ONE moving arrow */}
        <div className="w-full overflow-x-auto py-2">
          <svg
            viewBox="0 0 1260 330"
            className="w-full min-w-[900px] h-auto"
            preserveAspectRatio="xMidYMid meet"
          >
            <defs>
              {/* Background ambient grid */}
              <pattern id="flow-grid" width="30" height="30" patternUnits="userSpaceOnUse">
                <path d="M 30 0 L 0 0 0 30" fill="none" stroke="rgba(255, 255, 255, 0.03)" strokeWidth="1" />
              </pattern>

              {/* Glowing Filter for the single moving arrow */}
              <filter id="single-arrow-glow" x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur stdDeviation="4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>

              {/* Arrowhead marker for static junction tracks */}
              <marker
                id="static-arrow"
                viewBox="0 0 10 10"
                refX="7"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto"
              >
                <path d="M 0 1 L 8 5 L 0 9 z" fill="rgba(148, 163, 184, 0.4)" />
              </marker>
            </defs>

            {/* Ambient Background Grid */}
            <rect width="1260" height="330" fill="url(#flow-grid)" rx="16" />

            {/* ─── Static Continuous Backbone Line across Pipeline ─── */}
            <line
              x1="170"
              y1="177"
              x2="1090"
              y2="177"
              stroke="rgba(148, 163, 184, 0.2)"
              strokeWidth="3"
              strokeDasharray="6,4"
            />

            {/* Individual Inter-Node Connecting Arrows */}
            {[
              { x1: 170, x2: 215 },
              { x1: 345, x2: 390 },
              { x1: 520, x2: 565 },
              { x1: 695, x2: 740 },
              { x1: 870, x2: 915 },
              { x1: 1045, x2: 1090 },
            ].map((conn, idx) => (
              <line
                key={idx}
                x1={conn.x1}
                y1="177"
                x2={conn.x2}
                y2="177"
                stroke="rgba(56, 189, 248, 0.6)"
                strokeWidth="2.5"
                markerEnd="url(#static-arrow)"
              />
            ))}

            {/* ─── ONLY ONE MOVING ARROW ALONG THE RETRIEVAL PIPELINE ─── */}
            <g>
              {/* Single Glowing Moving Arrowhead */}
              <path
                d="M -12 -6 L 4 0 L -12 6 Z"
                fill="#38bdf8"
                filter="url(#single-arrow-glow)"
              >
                <animateMotion
                  path="M 170 177 L 1090 177"
                  dur="4.8s"
                  repeatCount="indefinite"
                  rotate="auto"
                  keyPoints="0;0.96;1"
                  keyTimes="0;0.92;1"
                />
                <animate
                  attributeName="opacity"
                  values="0;1;1;0"
                  dur="4.8s"
                  repeatCount="indefinite"
                  keyTimes="0;0.05;0.95;1"
                />
              </path>

              {/* Accompanying Laser Energy Pulse */}
              <circle r="4.5" fill="#06b6d4" filter="url(#single-arrow-glow)">
                <animateMotion
                  path="M 170 177 L 1090 177"
                  dur="4.8s"
                  repeatCount="indefinite"
                  keyPoints="0;0.96;1"
                  keyTimes="0;0.92;1"
                />
                <animate
                  attributeName="opacity"
                  values="0;1;1;0"
                  dur="4.8s"
                  repeatCount="indefinite"
                  keyTimes="0;0.05;0.95;1"
                />
              </circle>
            </g>

            {/* ─── 7 RAG Pipeline Nodes Fitted Inside with Cell Padding ─── */}
            {RAG_PIPELINE_NODES.map((node) => {
              const isSelected = selectedNode.id === node.id;

              return (
                <g
                  key={node.id}
                  onClick={() => setSelectedNode(node)}
                  className="cursor-pointer group"
                >
                  {/* Active highlight glow for selected node */}
                  {isSelected && (
                    <rect
                      x={node.x - 4}
                      y={node.y - 4}
                      width={node.width + 8}
                      height={node.height + 8}
                      rx="16"
                      fill="none"
                      stroke={node.color}
                      strokeWidth="2.5"
                      opacity="0.85"
                      className="animate-pulse"
                    />
                  )}

                  {/* Card Outer Shell with generous cell padding */}
                  <rect
                    x={node.x}
                    y={node.y}
                    width={node.width}
                    height={node.height}
                    rx="14"
                    fill={isSelected ? "rgba(30, 41, 59, 0.95)" : "rgba(15, 23, 42, 0.85)"}
                    stroke={isSelected ? node.color : "rgba(255, 255, 255, 0.15)"}
                    strokeWidth={isSelected ? "2" : "1.2"}
                    className="transition-all duration-200 group-hover:stroke-sky-400"
                  />

                  {/* Top Stage Pill (Cell Padding: 12px from top, 12px from left) */}
                  <rect
                    x={node.x + 12}
                    y={node.y + 12}
                    width="32"
                    height="18"
                    rx="6"
                    fill={node.color}
                    fillOpacity="0.18"
                    stroke={node.color}
                    strokeOpacity="0.4"
                    strokeWidth="1"
                  />
                  <text
                    x={node.x + 28}
                    y={node.y + 25}
                    textAnchor="middle"
                    fill={node.color}
                    fontSize="10"
                    fontWeight="bold"
                    fontFamily="monospace"
                  >
                    {node.stageNumber}
                  </text>

                  {/* Stage Icon Circle (Cell Padding: 12px from top, aligned to right) */}
                  <circle
                    cx={node.x + node.width - 24}
                    cy={node.y + 21}
                    r="12"
                    fill={node.color}
                    fillOpacity="0.2"
                    stroke={node.color}
                    strokeOpacity="0.5"
                    strokeWidth="1"
                  />
                  <foreignObject
                    x={node.x + node.width - 32}
                    y={node.y + 13}
                    width="16"
                    height="16"
                  >
                    <div className="flex items-center justify-center w-full h-full">
                      {renderIcon(node.iconName, node.color)}
                    </div>
                  </foreignObject>

                  {/* Card Title (High contrast) */}
                  <text
                    x={node.x + 12}
                    y={node.y + 60}
                    fill="#f8fafc"
                    fontSize="13"
                    fontWeight="bold"
                  >
                    {node.name}
                  </text>

                  {/* Subtitle */}
                  <text
                    x={node.x + 12}
                    y={node.y + 78}
                    fill="#94a3b8"
                    fontSize="10"
                    fontWeight="500"
                  >
                    {node.subtitle}
                  </text>

                  {/* Divider line inside card */}
                  <line
                    x1={node.x + 12}
                    y1={node.y + 92}
                    x2={node.x + node.width - 12}
                    y2={node.y + 92}
                    stroke="rgba(255, 255, 255, 0.08)"
                    strokeWidth="1"
                  />

                  {/* Tech Tag / Category */}
                  <text
                    x={node.x + 12}
                    y={node.y + 110}
                    fill="#64748b"
                    fontSize="9.5"
                    fontFamily="monospace"
                  >
                    {node.category.toUpperCase()}
                  </text>

                  {/* Latency Pill at bottom of card */}
                  <rect
                    x={node.x + 12}
                    y={node.y + 126}
                    width={node.width - 24}
                    height="22"
                    rx="6"
                    fill="rgba(255, 255, 255, 0.04)"
                    stroke="rgba(255, 255, 255, 0.08)"
                    strokeWidth="1"
                  />
                  <text
                    x={node.x + node.width / 2}
                    y={node.y + 141}
                    textAnchor="middle"
                    fill="#38bdf8"
                    fontSize="10"
                    fontWeight="600"
                    fontFamily="monospace"
                  >
                    {node.latency}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Legend / Flow Instruction */}
        <div className="flex items-center justify-between text-xs text-muted-foreground pt-3 border-t border-border/40 flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-sky-400 animate-ping" />
            <span>Single moving pulse demonstrates continuous vector & permission flow</span>
          </div>
          <span className="text-[11px] text-muted-foreground">Click any node to inspect technical metrics & security guarantees</span>
        </div>
      </div>

      {/* ─── Selected Node Technical Inspector Card ─── */}
      <Card className="rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white/95 dark:bg-[#141826]/90 backdrop-blur-2xl shadow-xl overflow-hidden p-5">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 border-b border-border/40 pb-4">
          <div className="flex items-center gap-3">
            <div
              className="p-3 rounded-2xl flex items-center justify-center shrink-0 border"
              style={{
                backgroundColor: `${selectedNode.color}15`,
                borderColor: `${selectedNode.color}40`,
              }}
            >
              {renderIcon(selectedNode.iconName, selectedNode.color)}
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <Badge
                  style={{
                    backgroundColor: `${selectedNode.color}20`,
                    color: selectedNode.color,
                    borderColor: `${selectedNode.color}40`,
                  }}
                  className="border text-[10px] font-mono"
                >
                  {selectedNode.stageBadge}
                </Badge>
                <h3 className="text-base font-bold text-foreground">
                  {selectedNode.name} — {selectedNode.subtitle}
                </h3>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {selectedNode.description}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-start md:self-auto">
            <Badge variant="outline" className="text-xs font-mono border-primary/40 text-primary">
              <Zap className="h-3 w-3 mr-1" />
              {selectedNode.latency}
            </Badge>
            <Badge variant="secondary" className="text-xs font-mono">
              {selectedNode.category.toUpperCase()}
            </Badge>
          </div>
        </div>

        {/* Detailed technical breakdown grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 text-xs">
          <div className="space-y-1">
            <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
              <Info className="h-3.5 w-3.5 text-cyan-400" />
              RAG Architectural Role
            </span>
            <p className="text-foreground leading-relaxed">
              {selectedNode.ragRole}
            </p>
          </div>

          <div className="space-y-1">
            <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
              <Lock className="h-3.5 w-3.5 text-amber-400" />
              Zero-Trust Security Guarantee
            </span>
            <p className="text-foreground leading-relaxed">
              {selectedNode.securityGuarantee}
            </p>
          </div>

          <div className="space-y-1">
            <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
              <Cpu className="h-3.5 w-3.5 text-purple-400" />
              Underlying Technology
            </span>
            <p className="text-foreground font-mono text-[11px] leading-relaxed">
              {selectedNode.tech}
            </p>
          </div>
        </div>

        {/* Inputs & Outputs bar */}
        <div className="mt-4 pt-3 border-t border-border/40 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs bg-muted/20 p-3 rounded-xl">
          <div>
            <span className="font-semibold text-muted-foreground">Input Data:</span>{" "}
            <span className="text-foreground font-mono text-[11px]">{selectedNode.inputs}</span>
          </div>
          <div>
            <span className="font-semibold text-muted-foreground">Output Artifact:</span>{" "}
            <span className="text-foreground font-mono text-[11px]">{selectedNode.outputs}</span>
          </div>
        </div>
      </Card>
    </div>
  );
}
