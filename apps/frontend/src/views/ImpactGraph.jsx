import { useEffect, useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  useEdgesState,
  useNodesState,
} from "reactflow";
import dagre from "dagre";
import "reactflow/dist/style.css";

import { useGraph, useRun } from "../api";
import { TIER_NODE_COLOR, TierChip } from "../components/TierChip";

const NODE_W = 210;
const NODE_H = 50;

// ──────────────────────────────────────────────────────────────────────
// Palette: nodes by category, edges by kind. Colors carry meaning.
// ──────────────────────────────────────────────────────────────────────

const NODE_PALETTE = {
  endpoint:   { fg: "#831843", bg: "#fdf2f8", border: "#ec4899", icon: "→" }, // pink
  function:   { fg: "#1e1b4b", bg: "#eef2ff", border: "#6366f1", icon: "ƒ" }, // indigo
  module:     { fg: "#0c4a6e", bg: "#e0f2fe", border: "#0284c7", icon: "⬚" }, // sky
  data_model: { fg: "#064e3b", bg: "#ecfdf5", border: "#10b981", icon: "▦" }, // green
  env_var:    { fg: "#78350f", bg: "#fffbeb", border: "#f59e0b", icon: "$" }, // amber
  config:     { fg: "#3f3f46", bg: "#f4f4f5", border: "#71717a", icon: "⚙" }, // zinc
  human_doc:  { fg: "#581c87", bg: "#faf5ff", border: "#a855f7", icon: "¶" }, // purple
  _default:   { fg: "#1f2937", bg: "#f9fafb", border: "#9ca3af", icon: "•" },
};

const EDGE_PALETTE = {
  calls:            { color: "#6366f1", style: "solid",  label: "calls" },     // indigo
  imports:          { color: "#0284c7", style: "dashed", label: "imports" },   // sky
  extends:          { color: "#7c3aed", style: "solid",  label: "extends" },   // violet
  implements:       { color: "#a855f7", style: "dotted", label: "implements" },// purple
  handles_endpoint: { color: "#ec4899", style: "solid",  label: "handles" },   // pink
  uses_model:       { color: "#10b981", style: "solid",  label: "uses" },      // green
  reads_env:        { color: "#f59e0b", style: "dashed", label: "reads" },     // amber
  configured_by:    { color: "#71717a", style: "dotted", label: "configured" },// zinc
  react_context:    { color: "#06b6d4", style: "dashed", label: "context" },   // cyan
  docker:           { color: "#0ea5e9", style: "solid",  label: "docker" },
  docker_compose:   { color: "#0284c7", style: "solid",  label: "compose" },
  kubernetes:       { color: "#3b82f6", style: "solid",  label: "k8s" },
  terraform:        { color: "#7c3aed", style: "solid",  label: "tf" },
  _default:         { color: "#94a3b8", style: "solid",  label: "" },
};

function nodeStyle(category, tierColor) {
  const p = NODE_PALETTE[category] || NODE_PALETTE._default;
  return {
    fg: tierColor || p.fg,
    bg: tierColor ? `${tierColor}1f` : p.bg,
    border: tierColor || p.border,
    icon: p.icon,
  };
}

function edgeStyle(kind, broken) {
  const p = EDGE_PALETTE[kind] || EDGE_PALETTE._default;
  if (broken) {
    return { stroke: "#dc2626", strokeDasharray: "6 4", strokeWidth: 2.4, label: p.label };
  }
  const dash =
    p.style === "dashed" ? "6 4" : p.style === "dotted" ? "2 4" : undefined;
  return { stroke: p.color, strokeDasharray: dash, strokeWidth: 1.6, label: p.label };
}

/**
 * /runs/:runId/graph — react-flow rendering of the artifact graph.
 *
 * If `?prRun=:id` is present in the query string, nodes get their tier
 * coloring (Direct=red, High=orange, Medium=yellow) and broken edges
 * (in base, missing in head) render as dashed-red — the "live edge break"
 * demo moment.
 */
export function ImpactGraph() {
  const { runId } = useParams();
  const [search] = useSearchParams();
  const prRunId = search.get("prRun");
  const runQ = useRun(Number(runId));
  const repoId = runQ.data?.repo_id;
  const graphQ = useGraph(repoId, prRunId ? Number(prRunId) : undefined);

  const laidOut = useMemo(
    () => layoutGraph(graphQ.data?.nodes || [], graphQ.data?.edges || []),
    [graphQ.data]
  );
  const { categoryCounts, kindCounts } = laidOut;

  // Controlled state — required so drag updates persist on the canvas.
  const [nodes, setNodes, onNodesChange] = useNodesState(laidOut.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(laidOut.edges);

  useEffect(() => {
    setNodes(laidOut.nodes);
    setEdges(laidOut.edges);
  }, [laidOut, setNodes, setEdges]);

  return (
    <div style={{ height: "calc(100vh - 56px)", display: "flex", flexDirection: "column" }}>
      <div
        style={{
          padding: "10px 16px",
          background: "var(--bg-elevated)",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexWrap: "wrap",
        }}
      >
        <Link
          to={`/runs/${runId}`}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 13,
            color: "var(--fg-muted)",
            textDecoration: "none",
            padding: "4px 10px",
            borderRadius: 999,
            border: "1px solid var(--border)",
            background: "var(--bg-subtle)",
          }}
          title="Back to documentation"
        >
          ← Documentation
        </Link>
        <strong style={{ color: "var(--fg)" }}>Architecture · run #{runId}</strong>
        {prRunId && <span style={{ color: "var(--fg-subtle)", fontSize: 12 }}>PR overlay: #{prRunId}</span>}
        {graphQ.data?.tier_counts && (
          <>
            <TierChip tier="Direct" count={graphQ.data.tier_counts.Direct || 0} />
            <TierChip tier="High" count={graphQ.data.tier_counts.High || 0} />
            <TierChip tier="Medium" count={graphQ.data.tier_counts.Medium || 0} />
          </>
        )}
        <span style={{ marginLeft: "auto", color: "var(--fg-subtle)", fontSize: 12 }}>
          {nodes.length} nodes · {edges.length} edges
        </span>
      </div>

      <Legend categoryCounts={categoryCounts} kindCounts={kindCounts} />

      <div style={{ flex: 1 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          minZoom={0.2}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          panOnDrag
        >
          <Background gap={18} color="#e5e7eb" />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}

function Legend({ categoryCounts, kindCounts }) {
  const cats = Object.keys(categoryCounts).filter((c) => categoryCounts[c] > 0);
  const kinds = Object.keys(kindCounts).filter((k) => kindCounts[k] > 0);
  if (!cats.length && !kinds.length) return null;
  return (
    <div
      style={{
        padding: "8px 16px",
        background: "var(--bg-sidebar)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        gap: 18,
        flexWrap: "wrap",
        fontSize: 11,
      }}
    >
      <LegendGroup title="Nodes">
        {cats.map((c) => {
          const p = NODE_PALETTE[c] || NODE_PALETTE._default;
          return (
            <span key={c} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: 3,
                  background: p.bg,
                  border: `1.5px solid ${p.border}`,
                }}
              />
              <span style={{ color: "var(--fg-muted)" }}>
                {c} <span style={{ color: "var(--fg-faint)" }}>· {categoryCounts[c]}</span>
              </span>
            </span>
          );
        })}
      </LegendGroup>
      <LegendGroup title="Edges">
        {kinds.map((k) => {
          const p = EDGE_PALETTE[k] || EDGE_PALETTE._default;
          const dash =
            p.style === "dashed" ? "4 3" : p.style === "dotted" ? "2 3" : "0";
          return (
            <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <svg width="22" height="6">
                <line
                  x1="0"
                  y1="3"
                  x2="22"
                  y2="3"
                  stroke={p.color}
                  strokeWidth="2"
                  strokeDasharray={dash}
                />
              </svg>
              <span style={{ color: "var(--fg-muted)" }}>
                {k} <span style={{ color: "var(--fg-faint)" }}>· {kindCounts[k]}</span>
              </span>
            </span>
          );
        })}
      </LegendGroup>
    </div>
  );
}

function LegendGroup({ title, children }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span
        style={{
          fontSize: 10,
          textTransform: "uppercase",
          letterSpacing: 0.5,
          color: "var(--fg-faint)",
          fontWeight: 600,
        }}
      >
        {title}
      </span>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>{children}</div>
    </div>
  );
}

function layoutGraph(rawNodes, rawEdges) {
  if (!rawNodes.length) {
    return { nodes: [], edges: [], categoryCounts: {}, kindCounts: {} };
  }
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 36, ranksep: 70 });
  for (const n of rawNodes) {
    g.setNode(n.id, { width: NODE_W, height: NODE_H });
  }
  for (const e of rawEdges) {
    g.setEdge(e.source, e.target);
  }
  dagre.layout(g);

  const categoryCounts = {};
  const nodes = rawNodes.map((n) => {
    categoryCounts[n.category] = (categoryCounts[n.category] || 0) + 1;
    const pos = g.node(n.id);
    const tierColor = n.tier ? TIER_NODE_COLOR[n.tier] : null;
    const ns = nodeStyle(n.category, tierColor);
    return {
      id: n.id,
      data: { label: nodeLabel(n, ns) },
      position: { x: pos?.x || 0, y: pos?.y || 0 },
      style: {
        width: NODE_W,
        background: ns.bg,
        border: `2px solid ${ns.border}`,
        borderRadius: 10,
        padding: "6px 10px",
        fontSize: 12,
        color: ns.fg,
        boxShadow: "0 1px 3px rgba(15,15,20,0.06)",
      },
    };
  });

  const kindCounts = {};
  const edges = rawEdges.map((e, i) => {
    kindCounts[e.kind] = (kindCounts[e.kind] || 0) + 1;
    const es = edgeStyle(e.kind, e.broken);
    return {
      id: `${e.source}->${e.target}-${i}`,
      source: e.source,
      target: e.target,
      label: es.label,
      labelStyle: { fill: es.stroke, fontSize: 10, fontWeight: 500 },
      labelBgStyle: { fill: "#ffffff", fillOpacity: 0.9 },
      labelBgPadding: [3, 2],
      labelBgBorderRadius: 3,
      animated: !!e.broken,
      style: {
        stroke: es.stroke,
        strokeWidth: es.strokeWidth,
        ...(es.strokeDasharray ? { strokeDasharray: es.strokeDasharray } : {}),
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: es.stroke },
    };
  });

  return { nodes, edges, categoryCounts, kindCounts };
}

function nodeLabel(n, ns) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span
        style={{
          width: 18,
          height: 18,
          borderRadius: 5,
          background: ns.border,
          color: "#fff",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 11,
          fontWeight: 700,
          flexShrink: 0,
        }}
      >
        {ns.icon}
      </span>
      <div style={{ display: "flex", flexDirection: "column", gap: 1, overflow: "hidden" }}>
        <div
          style={{
            fontWeight: 600,
            color: ns.fg,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {n.name}
        </div>
        <div
          style={{
            fontSize: 10,
            color: "var(--fg-subtle)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {n.category}
          {n.source_file ? ` · ${n.source_file.split("/").pop()}:${n.line || "?"}` : ""}
        </div>
      </div>
    </div>
  );
}
