import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { TierChip } from "./TierChip";

/**
 * Renders one DocDiff row from /pull-requests/:id/doc-diff:
 *   - Header: tier chip + change_type + doc path
 *   - Body:   side-by-side rendered Markdown — Before | After. Added blocks
 *             tinted green, removed blocks tinted red, so the change is
 *             visible as document, not as raw markdown source.
 */
export function DocDiff({ diff }) {
  const { beforeBlocks, afterBlocks } = useMemo(() => splitDiff(diff.side_by_side), [diff.side_by_side]);

  return (
    <div
      style={{
        marginBottom: 16,
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        overflow: "hidden",
        background: "#fff",
        minWidth: 0,
        maxWidth: "100%",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 14px",
          background: "#f9fafb",
          borderBottom: "1px solid #e5e7eb",
        }}
      >
        <TierChip tier={diff.impact_tier || "Medium"} />
        <span style={{ fontWeight: 600, fontSize: 13, color: "#374151" }}>{diff.change_type}</span>
        <code style={{ fontSize: 12, color: "#6b7280" }}>{diff.doc_path}</code>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", minWidth: 0 }}>
        <DiffPane label="Before" blocks={beforeBlocks} side="base" />
        <DiffPane label="After" blocks={afterBlocks} side="head" borderLeft />
      </div>
    </div>
  );
}

function DiffPane({ label, blocks, side, borderLeft = false }) {
  return (
    <div
      style={{
        borderLeft: borderLeft ? "1px solid #f3f4f6" : "none",
        display: "flex",
        flexDirection: "column",
        minHeight: 120,
        minWidth: 0,
        maxWidth: "100%",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "6px 12px",
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: 0.5,
          textTransform: "uppercase",
          color: side === "head" ? "#065f46" : "#7c2d12",
          background: side === "head" ? "#ecfdf5" : "#fef2f2",
          borderBottom: "1px solid #f3f4f6",
        }}
      >
        {label}
      </div>
      <div style={{ padding: "8px 14px", flex: 1, maxWidth: "100%", minWidth: 0, overflow: "auto" }}>
        {blocks.length === 0 ? (
          <p style={{ color: "#9ca3af", fontSize: 13, margin: 0 }}>(empty)</p>
        ) : (
          blocks.map((blk, i) => <Block key={i} block={blk} side={side} />)
        )}
      </div>
    </div>
  );
}

function Block({ block, side }) {
  const tone = blockTone(block.type, side);
  const md = block.lines.join("\n");
  if (!md.trim()) return null;
  return (
    <div
      style={{
        background: tone.bg,
        borderLeft: tone.border ? `3px solid ${tone.border}` : "none",
        padding: tone.bg ? "4px 10px" : 0,
        margin: "2px 0",
        borderRadius: 4,
      }}
    >
      <div
        className="md-render"
        style={{
          fontSize: 13,
          lineHeight: 1.55,
          color: "#1f2937",
          overflowWrap: "anywhere",
          wordBreak: "break-word",
        }}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{md}</ReactMarkdown>
      </div>
    </div>
  );
}

function blockTone(type, side) {
  if (type === "equal") return { bg: null, border: null };
  if (side === "head" && (type === "insert" || type === "replace")) {
    return { bg: "#ecfdf5", border: "#10b981" };
  }
  if (side === "base" && (type === "delete" || type === "replace")) {
    return { bg: "#fef2f2", border: "#ef4444" };
  }
  return { bg: null, border: null };
}

function splitDiff(side) {
  // side.rows: [{type, base:[lines], head:[lines]}]
  // Build sequence of blocks per pane preserving structure for ReactMarkdown.
  const beforeBlocks = [];
  const afterBlocks = [];
  if (!side?.rows) return { beforeBlocks, afterBlocks };
  for (const row of side.rows) {
    const baseLines = row.base || [];
    const headLines = row.head || [];
    if (baseLines.length) beforeBlocks.push({ type: row.type, lines: baseLines });
    if (headLines.length) afterBlocks.push({ type: row.type, lines: headLines });
  }
  return { beforeBlocks, afterBlocks };
}
