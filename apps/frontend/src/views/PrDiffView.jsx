import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { usePrDocDiff, usePrImpact } from "../api";
import { DocDiff } from "../components/DocDiff";
import { TierChip } from "../components/TierChip";

const TIER_FILTERS = ["All", "Direct", "High", "Medium"];

/**
 * /prs/:pullRequestId — three-panel diff view:
 *   - Header: tier counts + filter chips + "Open shadow PR" link
 *   - Body:   list of DocDiff cards filtered by tier
 */
export function PrDiffView() {
  const { pullRequestId } = useParams();
  const numericId = Number(pullRequestId);
  const impactQ = usePrImpact(numericId);
  const diffQ = usePrDocDiff(numericId);
  const [filter, setFilter] = useState("All");
  const [splitView, setSplitView] = useState(true);

  const allDiffs = diffQ.data?.diffs || [];
  const counts = impactQ.data?.impact_summary?.tier_counts || diffQ.data?.tier_counts || {};
  const shadowPr = impactQ.data?.shadow_pr;
  const filtered = useMemo(
    () => (filter === "All" ? allDiffs : allDiffs.filter((d) => d.impact_tier === filter)),
    [allDiffs, filter]
  );

  return (
    <div style={{ padding: 16 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: 12,
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          marginBottom: 16,
        }}
      >
        <h2 style={{ margin: 0 }}>PR #{pullRequestId}</h2>
        <TierChip tier="Direct" count={counts.Direct || 0} />
        <TierChip tier="High" count={counts.High || 0} />
        <TierChip tier="Medium" count={counts.Medium || 0} />
        <span style={{ color: "#6b7280" }}>
          {allDiffs.length} doc diff{allDiffs.length === 1 ? "" : "s"}
        </span>
        {shadowPr && (
          <a
            href={shadowPr.url}
            target="_blank"
            rel="noreferrer"
            style={{
              padding: "4px 10px",
              borderRadius: 6,
              background: "#1d4ed8",
              color: "#fff",
              fontSize: 12,
              textDecoration: "none",
            }}
            title={`Shadow branch: ${shadowPr.branch} · ${shadowPr.file_count} files`}
          >
            📚 Shadow PR
          </a>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {TIER_FILTERS.map((t) => (
            <button
              key={t}
              onClick={() => setFilter(t)}
              style={{
                padding: "4px 12px",
                borderRadius: 6,
                border: "1px solid #d1d5db",
                background: filter === t ? "#1f2937" : "#fff",
                color: filter === t ? "#fff" : "#374151",
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              {t}
            </button>
          ))}
          <button
            onClick={() => setSplitView((v) => !v)}
            style={{
              padding: "4px 12px",
              borderRadius: 6,
              border: "1px solid #d1d5db",
              background: "#fff",
              cursor: "pointer",
              fontSize: 13,
            }}
            title="Toggle split / unified view"
          >
            {splitView ? "Split" : "Unified"}
          </button>
        </div>
      </div>

      {impactQ.data?.review_comment_body && (
        <pre
          style={{
            background: "#fff7ed",
            border: "1px solid #fed7aa",
            padding: 12,
            borderRadius: 8,
            marginBottom: 16,
            whiteSpace: "pre-wrap",
            fontFamily: "ui-monospace, monospace",
            fontSize: 12,
          }}
        >
          {impactQ.data.review_comment_body}
        </pre>
      )}

      {diffQ.isLoading && <p>Loading diffs…</p>}
      {!diffQ.isLoading && filtered.length === 0 && (
        <p style={{ color: "#6b7280" }}>No diffs match this filter.</p>
      )}
      {filtered.map((d) => (
        <DocDiff key={d.artifact_id} diff={d} splitView={splitView} />
      ))}
    </div>
  );
}
