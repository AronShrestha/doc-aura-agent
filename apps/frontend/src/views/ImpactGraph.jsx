import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  useEdgesState,
  useNodesState,
  useStore,
} from "reactflow";
import dagre from "dagre";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from "d3-force";
import "reactflow/dist/style.css";

import { useGraph, useRun } from "../api";
import { TIER_NODE_COLOR, TierChip } from "../components/TierChip";

const NODE_W = 210;
const NODE_H = 50;
const NODE_COMPACT_SIZE = 32;
const ZOOM_LABEL_THRESHOLD = 0.65;
const zoomSelector = (s) => s.transform[2];

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

function nodeStyle(category, tierColor, isNew) {
  const p = NODE_PALETTE[category] || NODE_PALETTE._default;
  if (isNew) {
    return {
      fg: "#064e3b",
      bg: "#ecfdf5",
      border: "#10b981",
      icon: p.icon,
      borderStyle: "dashed",
      borderWidth: 3,
    };
  }
  return {
    fg: tierColor || p.fg,
    bg: tierColor ? `${tierColor}1f` : p.bg,
    border: tierColor || p.border,
    icon: p.icon,
  };
}

function edgeStyle(kind, broken, isNew) {
  const p = EDGE_PALETTE[kind] || EDGE_PALETTE._default;
  if (broken) {
    return { stroke: "#dc2626", strokeDasharray: "6 4", strokeWidth: 2.4, label: p.label };
  }
  if (isNew) {
    return { stroke: "#10b981", strokeDasharray: "8 4", strokeWidth: 2.6, label: p.label };
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
export function ImpactGraph({ runIdOverride, prRunIdOverride, repoIdOverride } = {}) {
  const params = useParams();
  const [search] = useSearchParams();
  const runId = runIdOverride ?? params.runId;
  const prRunId = prRunIdOverride ?? search.get("prRun");
  const runQ = useRun(Number(runId), { enabled: !!runId && !repoIdOverride });
  const repoId = repoIdOverride ?? runQ.data?.repo_id;
  const graphQ = useGraph(repoId, prRunId ? Number(prRunId) : undefined);

  // When a PR overlay is present (prRunId), default to "blast radius" view —
  // only show nodes the PR actually affects. Click the eye to reveal the
  // rest of the graph greyed out behind it.
  const hasPrOverlay = !!prRunId;
  const [showAll, setShowAll] = useState(false);
  const blastRadiusActive = hasPrOverlay && !showAll;

  const rawNodes = graphQ.data?.nodes || [];
  const rawEdges = graphQ.data?.edges || [];
  const { affectedIds, impactScore, summary } = useMemo(
    () => computeImpact(rawNodes, rawEdges),
    [rawNodes, rawEdges]
  );

  const laidOut = useMemo(
    () => layoutGraph(rawNodes, rawEdges, {
      affectedIds,
      filter: blastRadiusActive,
      dim: hasPrOverlay && showAll,
    }),
    [rawNodes, rawEdges, affectedIds, blastRadiusActive, hasPrOverlay, showAll]
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
        {hasPrOverlay && <ImpactScoreChip score={impactScore} summary={summary} />}
        <span style={{ marginLeft: "auto", color: "var(--fg-subtle)", fontSize: 12 }}>
          {nodes.length} nodes · {edges.length} edges
          {blastRadiusActive && rawNodes.length > nodes.length && (
            <span style={{ marginLeft: 6, color: "var(--fg-faint)" }}>
              ({rawNodes.length - nodes.length} hidden)
            </span>
          )}
        </span>
      </div>

      <Legend categoryCounts={categoryCounts} kindCounts={kindCounts} />

      <div style={{ flex: 1, position: "relative" }}>
        {hasPrOverlay && (
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            title={showAll ? "Hide unaffected nodes" : "Reveal full graph (greyed out)"}
            aria-label={showAll ? "Hide unaffected nodes" : "Reveal full graph"}
            style={{
              position: "absolute",
              top: 14,
              right: 14,
              zIndex: 5,
              width: 44,
              height: 44,
              borderRadius: 10,
              border: `1.5px solid ${showAll ? "var(--accent)" : "var(--border-strong)"}`,
              background: showAll ? "var(--accent)" : "var(--bg-elevated)",
              color: showAll ? "#fff" : "var(--fg-muted)",
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 2px 6px rgba(15,15,20,0.08)",
              transition: "background 120ms, color 120ms, border-color 120ms",
            }}
          >
            <EyeIcon open={showAll} />
          </button>
        )}
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          fitViewOptions={{ padding: 0.02, includeHiddenNodes: true, minZoom: 0.7 }}
          minZoom={0.05}
          maxZoom={2.5}
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

const MIN_NODE_GAP_X = 16;       // minimum horizontal gap between nodes (compact)
const SUB_ROW_GAP = 16;          // small vertical gap between wrapped sub-rows of the SAME rank
const RANK_GAP = 90;             // big vertical gap between DIFFERENT ranks (segregates levels)
const MAX_PER_ROW = 50;

function computeHierarchyWrap(rawNodes, rawEdges) {
  // Compute longest-path depth per node using a topological-style BFS.
  // Source nodes (no incoming edges) start at depth 0; downstream nodes
  // sit at max(depth(parent)) + 1. Cycles are broken by clamping.
  const out = new Map();
  const incoming = new Map();
  for (const n of rawNodes) {
    out.set(n.id, []);
    incoming.set(n.id, 0);
  }
  for (const e of rawEdges) {
    if (out.has(e.source) && incoming.has(e.target) && e.source !== e.target) {
      out.get(e.source).push(e.target);
      incoming.set(e.target, (incoming.get(e.target) || 0) + 1);
    }
  }
  const depth = new Map(rawNodes.map((n) => [n.id, 0]));
  const queue = rawNodes.filter((n) => (incoming.get(n.id) || 0) === 0).map((n) => n.id);
  const visited = new Map(queue.map((id) => [id, 0]));
  let safety = rawNodes.length * 4;
  while (queue.length && safety-- > 0) {
    const id = queue.shift();
    const d = depth.get(id) || 0;
    for (const next of out.get(id) || []) {
      const cand = d + 1;
      if (cand > (depth.get(next) || 0)) {
        depth.set(next, cand);
        const visits = (visited.get(next) || 0) + 1;
        visited.set(next, visits);
        if (visits < 8) queue.push(next);
      }
    }
  }

  // Bucket by depth.
  const byDepth = new Map();
  for (const n of rawNodes) {
    const d = depth.get(n.id) || 0;
    if (!byDepth.has(d)) byDepth.set(d, []);
    byDepth.get(d).push(n);
  }

  // Layout width = widest *row* (after wrap cap) × (NODE_W + gap).
  // A rank larger than MAX_PER_ROW is split into multiple sub-rows of up
  // to MAX_PER_ROW nodes each. The shared layoutWidth equals the widest
  // single row that exists, so spreading is uniform and predictable.
  const ranks = [...byDepth.keys()].sort((a, b) => a - b);
  const widestRow = Math.min(
    MAX_PER_ROW,
    Math.max(...ranks.map((r) => byDepth.get(r).length)),
  );
  const layoutWidth = Math.max(NODE_W * 2, widestRow * (NODE_W + MIN_NODE_GAP_X));

  const pos = new Map();
  let y = 0;
  for (let r = 0; r < ranks.length; r++) {
    const arr = byDepth.get(ranks[r]);
    const subRows = Math.max(1, Math.ceil(arr.length / MAX_PER_ROW));
    for (let row = 0; row < subRows; row++) {
      const slice = arr.slice(row * MAX_PER_ROW, (row + 1) * MAX_PER_ROW);
      if (slice.length === 1) {
        pos.set(slice[0].id, { x: -NODE_W / 2, y });
      } else {
        const usableW = layoutWidth - NODE_W;
        const step = usableW / (slice.length - 1);
        const startX = -layoutWidth / 2;
        for (let i = 0; i < slice.length; i++) {
          pos.set(slice[i].id, {
            x: startX + i * step,
            y,
          });
        }
      }
      const isLastSubRow = row === subRows - 1;
      y += NODE_H + (isLastSubRow ? RANK_GAP : SUB_ROW_GAP);
    }
  }
  return pos;
}

const TIER_WEIGHT = { Direct: 3, High: 2, Medium: 1 };

function computeImpact(rawNodes, rawEdges) {
  const affectedIds = new Set();
  const tierCounts = { Direct: 0, High: 0, Medium: 0, New: 0 };
  let weightSum = 0;
  for (const n of rawNodes) {
    let w = TIER_WEIGHT[n.tier] || 0;
    if (!w && n.is_new) w = 1;
    if (w > 0) {
      affectedIds.add(n.id);
      weightSum += w;
      if (n.tier && tierCounts[n.tier] != null) tierCounts[n.tier] += 1;
      else if (n.is_new) tierCounts.New += 1;
    }
  }
  let brokenEdges = 0;
  let newEdges = 0;
  for (const e of rawEdges) {
    if (e.broken) {
      brokenEdges += 1;
      affectedIds.add(e.source);
      affectedIds.add(e.target);
    }
    if (e.is_new) {
      newEdges += 1;
      affectedIds.add(e.source);
      affectedIds.add(e.target);
    }
  }
  const total = rawNodes.length;
  const max = total * (TIER_WEIGHT.Direct || 3);
  const score = total > 0 ? Math.round((weightSum / max) * 100) : 0;

  // Per-category affected breakdown for the tooltip.
  const categoryCounts = {};
  const topNodes = [];
  for (const n of rawNodes) {
    if (!affectedIds.has(n.id)) continue;
    const cat = n.category || "other";
    categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
    topNodes.push({
      name: n.name,
      category: n.category,
      tier: n.tier,
      is_new: n.is_new,
      weight: TIER_WEIGHT[n.tier] || (n.is_new ? 1 : 0),
    });
  }
  topNodes.sort((a, b) => (b.weight - a.weight) || a.name.localeCompare(b.name));

  return {
    affectedIds,
    impactScore: Math.max(0, Math.min(100, score)),
    summary: {
      total,
      affected: affectedIds.size,
      tierCounts,
      categoryCounts,
      brokenEdges,
      newEdges,
      topNodes: topNodes.slice(0, 6),
    },
  };
}

function layoutGraph(rawNodes, rawEdges, opts = {}) {
  if (!rawNodes.length) {
    return { nodes: [], edges: [], categoryCounts: {}, kindCounts: {} };
  }
  const { affectedIds = null, filter = false, dim = false } = opts;

  // In filter mode, only affected nodes (+ their connecting edges) reach the
  // canvas. In dim mode, everything stays but unaffected items go translucent.
  const visibleNodes = filter && affectedIds
    ? rawNodes.filter((n) => affectedIds.has(n.id))
    : rawNodes;
  const visibleNodeIds = new Set(visibleNodes.map((n) => n.id));
  const visibleEdges = filter && affectedIds
    ? rawEdges.filter((e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target))
    : rawEdges;

  const positions = computeHierarchyWrap(visibleNodes, visibleEdges);

  const categoryCounts = {};
  const nodes = visibleNodes.map((n) => {
    categoryCounts[n.category] = (categoryCounts[n.category] || 0) + 1;
    const tierColor = n.tier ? TIER_NODE_COLOR[n.tier] : null;
    const ns = nodeStyle(n.category, tierColor, n.is_new);
    const isAffected = affectedIds ? affectedIds.has(n.id) : true;
    const dimmed = dim && !isAffected;
    const classNames = [];
    if (!dimmed) {
      if (n.tier === "Direct") classNames.push("node-pulse-direct");
      if (n.is_new) classNames.push("node-pulse-new");
    }
    if (dimmed) classNames.push("node-dimmed");
    const p = positions.get(n.id) || { x: 0, y: 0 };
    return {
      id: n.id,
      type: "aura",
      data: { node: n, ns, dimmed },
      position: { x: p.x, y: p.y },
      className: classNames.join(" ") || undefined,
    };
  });

  const kindCounts = {};
  const edges = visibleEdges.map((e, i) => {
    kindCounts[e.kind] = (kindCounts[e.kind] || 0) + 1;
    const es = edgeStyle(e.kind, e.broken, e.is_new);
    const endpointsAffected = affectedIds
      ? affectedIds.has(e.source) && affectedIds.has(e.target)
      : true;
    const dimmed = dim && !endpointsAffected && !e.broken && !e.is_new;
    return {
      id: `${e.source}->${e.target}-${i}`,
      source: e.source,
      target: e.target,
      label: dimmed ? undefined : es.label,
      labelStyle: { fill: es.stroke, fontSize: 10, fontWeight: 500 },
      labelBgStyle: { fill: "#ffffff", fillOpacity: 0.9 },
      labelBgPadding: [3, 2],
      labelBgBorderRadius: 3,
      animated: !dimmed && !!(e.broken || e.is_new),
      style: {
        stroke: es.stroke,
        strokeWidth: es.strokeWidth,
        opacity: dimmed ? 0.18 : 1,
        ...(es.strokeDasharray ? { strokeDasharray: es.strokeDasharray } : {}),
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: es.stroke },
    };
  });

  return { nodes, edges, categoryCounts, kindCounts };
}

function ImpactScoreChip({ score, summary }) {
  const [open, setOpen] = useState(false);
  const color =
    score >= 70 ? "#dc2626" : score >= 40 ? "#ea580c" : score >= 15 ? "#ca8a04" : "#16a34a";
  const bg =
    score >= 70 ? "#fef2f2" : score >= 40 ? "#fff7ed" : score >= 15 ? "#fefce8" : "#f0fdf4";
  return (
    <span
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      tabIndex={0}
      style={{
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 10px 3px 8px",
        borderRadius: 999,
        border: `1.5px solid ${color}`,
        background: bg,
        color,
        fontSize: 12,
        fontWeight: 600,
        cursor: "help",
        outline: "none",
      }}
    >
      <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.4, opacity: 0.85 }}>
        Impact
      </span>
      <span style={{ fontSize: 14, fontWeight: 700 }}>{score}</span>
      <span style={{ fontSize: 10, opacity: 0.7 }}>/100</span>
      {open && summary && (
        <ImpactTooltip score={score} summary={summary} accent={color} />
      )}
    </span>
  );
}

function impactSeverityLabel(score) {
  if (score === 0) return "No measurable impact";
  if (score < 15) return "Low impact — narrow blast radius";
  if (score < 40) return "Moderate impact";
  if (score < 70) return "High impact — significant reach";
  return "Critical impact — broad reach";
}

function ImpactTooltip({ score, summary, accent }) {
  const { total, affected, tierCounts, categoryCounts, brokenEdges, newEdges, topNodes } = summary;
  const pctAffected = total > 0 ? Math.round((affected / total) * 100) : 0;
  const tierRows = [
    { label: "Direct", count: tierCounts.Direct, swatch: "#dc2626" },
    { label: "High", count: tierCounts.High, swatch: "#ea580c" },
    { label: "Medium", count: tierCounts.Medium, swatch: "#ca8a04" },
    { label: "New", count: tierCounts.New, swatch: "#10b981" },
  ].filter((r) => r.count > 0);

  const topCats = Object.entries(categoryCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);

  return (
    <div
      role="tooltip"
      style={{
        position: "absolute",
        top: "calc(100% + 8px)",
        left: 0,
        zIndex: 50,
        width: 320,
        background: "#ffffff",
        color: "var(--fg)",
        border: "1px solid var(--border-strong)",
        borderTop: `3px solid ${accent}`,
        borderRadius: 8,
        boxShadow: "0 10px 30px rgba(15,15,20,0.18)",
        padding: "12px 14px",
        fontSize: 12,
        lineHeight: 1.5,
        fontWeight: 400,
        textTransform: "none",
        letterSpacing: 0,
        whiteSpace: "normal",
      }}
    >
      <div style={{ fontWeight: 700, color: accent, fontSize: 13, marginBottom: 2 }}>
        {impactSeverityLabel(score)}
      </div>
      <div style={{ color: "var(--fg-muted)", marginBottom: 10 }}>
        <strong style={{ color: "var(--fg)" }}>{affected}</strong> of {total} nodes affected
        ({pctAffected}% of graph). Score is weighted by tier severity, so a few Direct hits can
        outweigh many Medium ones.
      </div>

      {tierRows.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--fg-faint)", fontWeight: 600, marginBottom: 4 }}>
            Tier breakdown
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {tierRows.map((t) => (
              <span key={t.label} style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "2px 8px", borderRadius: 999, background: "#f4f4f5", color: "#1f2937", fontSize: 11 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: t.swatch }} />
                {t.label} · <strong>{t.count}</strong>
              </span>
            ))}
          </div>
        </div>
      )}

      {topCats.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--fg-faint)", fontWeight: 600, marginBottom: 4 }}>
            Sections affected
          </div>
          <div style={{ color: "var(--fg-muted)" }}>
            {topCats.map(([cat, n], i) => (
              <span key={cat}>
                <strong style={{ color: "var(--fg)" }}>{cat}</strong> ({n})
                {i < topCats.length - 1 ? ", " : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      {topNodes.length > 0 && (
        <div style={{ marginBottom: (brokenEdges || newEdges) ? 10 : 0 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--fg-faint)", fontWeight: 600, marginBottom: 4 }}>
            Most impacted
          </div>
          <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 2 }}>
            {topNodes.map((n) => (
              <li key={n.name} style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--fg-muted)" }}>
                <span style={{ fontSize: 10, color: "var(--fg-faint)", minWidth: 50 }}>
                  {n.tier || (n.is_new ? "New" : "—")}
                </span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--fg)" }}>
                  {n.name}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(brokenEdges > 0 || newEdges > 0) && (
        <div style={{ color: "var(--fg-muted)", borderTop: "1px solid var(--border)", paddingTop: 8, fontSize: 11 }}>
          {brokenEdges > 0 && <span style={{ color: "#dc2626", fontWeight: 600 }}>{brokenEdges} broken edge{brokenEdges === 1 ? "" : "s"}</span>}
          {brokenEdges > 0 && newEdges > 0 && " · "}
          {newEdges > 0 && <span style={{ color: "#16a34a", fontWeight: 600 }}>{newEdges} new edge{newEdges === 1 ? "" : "s"}</span>}
        </div>
      )}
    </div>
  );
}

function EyeIcon({ open }) {
  if (open) {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    );
  }
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a19.5 19.5 0 0 1 4.22-5.16" />
      <path d="M9.9 4.24A10.94 10.94 0 0 1 12 4c7 0 11 8 11 8a19.6 19.6 0 0 1-3.17 4.36" />
      <path d="M9.88 9.88a3 3 0 0 0 4.24 4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

function AuraNode({ data }) {
  const { node: n, ns, dimmed } = data;
  const zoom = useStore(zoomSelector);
  const compact = zoom < ZOOM_LABEL_THRESHOLD;
  const dimStyle = dimmed
    ? { opacity: 0.22, filter: "grayscale(0.85)" }
    : null;

  if (compact) {
    return (
      <div
        title={`${n.name} · ${n.category}`}
        style={{
          width: NODE_COMPACT_SIZE,
          height: NODE_COMPACT_SIZE,
          background: ns.bg,
          border: `${ns.borderWidth || 2}px ${ns.borderStyle || "solid"} ${ns.border}`,
          borderRadius: 8,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: ns.fg,
          fontSize: 14,
          fontWeight: 700,
          boxShadow: "0 1px 3px rgba(15,15,20,0.06)",
          ...dimStyle,
        }}
      >
        <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
        <span>{ns.icon}</span>
        <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      </div>
    );
  }

  return (
    <div
      style={{
        width: NODE_W,
        background: ns.bg,
        border: `${ns.borderWidth || 2}px ${ns.borderStyle || "solid"} ${ns.border}`,
        borderRadius: 10,
        padding: "6px 10px",
        fontSize: 12,
        color: ns.fg,
        boxShadow: "0 1px 3px rgba(15,15,20,0.06)",
        display: "flex",
        alignItems: "center",
        gap: 8,
        ...dimStyle,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
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
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}

const NODE_TYPES = { aura: AuraNode };
