import ReactDiffViewer from "react-diff-viewer-continued";
import { TierChip } from "./TierChip";

/**
 * Renders one DocDiff row from /pull-requests/:id/doc-diff:
 *   - Header: tier chip + change_type + doc path
 *   - Body:   side-by-side (default) or unified diff via react-diff-viewer
 */
export function DocDiff({ diff, splitView = true }) {
  const before = diff.side_by_side
    ? extractText(diff.side_by_side, "base")
    : "";
  const after = diff.side_by_side
    ? extractText(diff.side_by_side, "head")
    : "";

  return (
    <div
      style={{
        marginBottom: 16,
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        overflow: "hidden",
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
        <span style={{ fontWeight: 600, fontSize: 13, color: "#374151" }}>
          {diff.change_type}
        </span>
        <code style={{ fontSize: 12, color: "#6b7280" }}>{diff.doc_path}</code>
      </div>
      <ReactDiffViewer
        oldValue={before}
        newValue={after}
        splitView={splitView}
        useDarkTheme={false}
        showDiffOnly={false}
      />
    </div>
  );
}

function extractText(side, key) {
  if (!side?.rows) return "";
  const lines = [];
  for (const row of side.rows) {
    for (const line of row[key] || []) {
      lines.push(line);
    }
  }
  return lines.join("\n");
}
