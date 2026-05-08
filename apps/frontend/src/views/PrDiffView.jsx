import { useEffect, useMemo, useState } from "react";
import ReactDiffViewer from "react-diff-viewer-continued";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { reAnalyzePr, useAffectedDocs, useCodeDiff, usePrDocDiff, usePrImpact } from "../api";
import { DocDiff } from "../components/DocDiff";
import { TierChip } from "../components/TierChip";

/**
 * /prs/:pullRequestId — immersive two-pane PR review.
 *
 * Layout:
 *   - Header: tier counts, "Open shadow PR" link, mismatch banner, prev/next nav
 *   - Body:   left = code patch (GitHub Compare API), right = doc diff
 *
 * Query string ``?diff=:artifact_id`` selects the active diff. Prev/Next
 * arrows + ←/→ keys cycle through the affected-docs ordered list.
 */
export function PrDiffView({ pullRequestIdOverride } = {}) {
  const params = useParams();
  const [search, setSearch] = useSearchParams();
  const pullRequestId = pullRequestIdOverride ?? params.pullRequestId;
  const numericId = Number(pullRequestId);

  const impactQ = usePrImpact(numericId);
  const diffQ = usePrDocDiff(numericId);
  const codeQ = useCodeDiff(numericId);
  const affectedQ = useAffectedDocs(numericId);

  const allDiffs = diffQ.data?.diffs || [];
  const ordered = affectedQ.data?.items || [];
  const counts = impactQ.data?.impact_summary?.tier_counts || diffQ.data?.tier_counts || {};
  const shadowPr = impactQ.data?.shadow_pr;
  const patches = codeQ.data?.patches || {};

  const activeArtifactId = search.get("diff") || ordered[0]?.artifact_id || allDiffs[0]?.artifact_id || "";
  const activeIdx = useMemo(
    () => ordered.findIndex((it) => it.artifact_id === activeArtifactId),
    [ordered, activeArtifactId]
  );
  const activeItem = activeIdx >= 0 ? ordered[activeIdx] : null;
  const activeDiff = useMemo(
    () => allDiffs.find((d) => d.artifact_id === activeArtifactId),
    [allDiffs, activeArtifactId]
  );
  const activePatches = useMemo(() => {
    const files = activeItem?.source_files || [];
    return files.map((f) => ({ file: f, patch: patches[f] || "" })).filter((x) => x.patch);
  }, [activeItem, patches]);

  function setActive(artifactId) {
    const next = new URLSearchParams(search);
    if (artifactId) next.set("diff", artifactId);
    else next.delete("diff");
    setSearch(next, { replace: true });
  }

  function step(delta) {
    if (!ordered.length) return;
    const next = (activeIdx + delta + ordered.length) % ordered.length;
    setActive(ordered[next].artifact_id);
  }

  useEffect(() => {
    function onKey(e) {
      if (e.target?.tagName === "INPUT" || e.target?.tagName === "TEXTAREA") return;
      if (e.key === "ArrowLeft") step(-1);
      if (e.key === "ArrowRight") step(1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIdx, ordered.length]);

  const mismatchFlags = impactQ.data?.mismatch_flags;
  const hasMismatch = !!mismatchFlags?.any;
  const prMeta = impactQ.data?.pull_request;

  const queryClient = useQueryClient();
  const [reAnalyzing, setReAnalyzing] = useState(false);
  async function handleReAnalyze() {
    if (reAnalyzing) return;
    setReAnalyzing(true);
    try {
      await reAnalyzePr(numericId);
    } catch (err) {
      console.error("re-analyze failed", err);
      setReAnalyzing(false);
      return;
    }
    let attempts = 0;
    const poll = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ["pr-impact", numericId] });
      queryClient.invalidateQueries({ queryKey: ["pr-doc-diff", numericId] });
      queryClient.invalidateQueries({ queryKey: ["pr-affected-docs", numericId] });
      queryClient.invalidateQueries({ queryKey: ["pr-code-diff", numericId] });
      attempts += 1;
      if (attempts > 20) {
        clearInterval(poll);
        setReAnalyzing(false);
      }
    }, 5000);
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
        padding: 16,
        gap: 12,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: 12,
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          flexWrap: "wrap",
          flexShrink: 0,
        }}
      >
        <h2 style={{ margin: 0 }}>PR #{prMeta?.number ?? pullRequestId}</h2>
        {prMeta?.title && (
          <span style={{ color: "#374151", fontSize: 14, maxWidth: 360, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {prMeta.title}
          </span>
        )}
        {prMeta?.html_url && (
          <a
            href={prMeta.html_url}
            target="_blank"
            rel="noreferrer"
            title="Open PR on GitHub"
            style={{
              padding: "4px 10px",
              borderRadius: 6,
              background: "#1f2937",
              color: "#fff",
              fontSize: 12,
              textDecoration: "none",
            }}
          >
            ↗ GitHub
          </a>
        )}
        {prMeta?.merged && (
          <span style={{ fontSize: 12, color: "#581c87", background: "#faf5ff", border: "1px solid #d8b4fe", padding: "2px 8px", borderRadius: 999 }}>
            merged
          </span>
        )}
        <button
          onClick={handleReAnalyze}
          disabled={reAnalyzing}
          title="Re-run the PR orchestrator (1-3 min)"
          style={{
            padding: "4px 10px",
            borderRadius: 6,
            border: "1px solid #d1d5db",
            background: reAnalyzing ? "#f3f4f6" : "#fff",
            color: reAnalyzing ? "#9ca3af" : "#374151",
            cursor: reAnalyzing ? "wait" : "pointer",
            fontSize: 12,
          }}
        >
          {reAnalyzing ? "↻ Re-analyzing…" : "↻ Re-analyze PR"}
        </button>
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
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <button onClick={() => step(-1)} disabled={!ordered.length} style={navBtnStyle(!ordered.length)}>
            ◀ Prev
          </button>
          <span style={{ fontSize: 12, color: "#6b7280", minWidth: 80, textAlign: "center" }}>
            {activeIdx >= 0 ? `${activeIdx + 1} of ${ordered.length}` : "—"}
          </span>
          <button onClick={() => step(1)} disabled={!ordered.length} style={navBtnStyle(!ordered.length)}>
            Next ▶
          </button>
        </div>
      </div>

      {hasMismatch && (
        <div
          style={{
            padding: 10,
            borderRadius: 8,
            background: "#fef3c7",
            border: "1px solid #fcd34d",
            color: "#7c2d12",
            fontSize: 13,
            flexShrink: 0,
          }}
        >
          ⚠ Documentation mismatch detected:{" "}
          {(mismatchFlags.undocumented_endpoint?.length || 0)} undocumented endpoint(s),{" "}
          {(mismatchFlags.undocumented_data_model?.length || 0)} undocumented data model(s),{" "}
          {(mismatchFlags.direct_or_high_doc_diff?.length || 0)} Direct/High doc diff(s).
        </div>
      )}

      {activeItem && (
        <div style={{ fontSize: 12, color: "#6b7280", flexShrink: 0 }}>
          <strong style={{ color: "#1f2937" }}>{activeItem.impact_tier}</strong>
          {" · "}
          <code>{activeItem.doc_path}</code>
          {activeItem.source_files?.length ? (
            <>
              {" · "}
              <code>{activeItem.source_files.join(", ")}</code>
            </>
          ) : null}
        </div>
      )}

      {ordered.length > 0 && (
        <details style={{ flexShrink: 0 }}>
          <summary style={{ cursor: "pointer", color: "#6b7280", fontSize: 13 }}>
            All affected docs ({ordered.length})
          </summary>
          <div style={{ display: "grid", gap: 4, marginTop: 8 }}>
            {ordered.map((it, i) => (
              <button
                key={it.artifact_id}
                onClick={() => setActive(it.artifact_id)}
                style={{
                  textAlign: "left",
                  padding: "6px 10px",
                  borderRadius: 6,
                  background: it.artifact_id === activeArtifactId ? "#eef2ff" : "#fff",
                  border: it.artifact_id === activeArtifactId ? "1px solid #6366f1" : "1px solid #e5e7eb",
                  cursor: "pointer",
                  fontSize: 13,
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                }}
              >
                <span style={{ minWidth: 28, color: "#9ca3af", fontFamily: "ui-monospace, monospace", fontSize: 11 }}>
                  {i + 1}
                </span>
                <TierChip tier={it.impact_tier || "Medium"} />
                <code style={{ color: "#374151" }}>{it.doc_path}</code>
              </button>
            ))}
          </div>
        </details>
      )}

      <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, overflow: "hidden" }}>
        <section style={paneShellStyle}>
          <header style={paneHeader("#0c4a6e", "#e0f2fe", "#0284c7")}>Code change</header>
          <div style={{ flex: 1, overflow: "auto", minHeight: 0 }}>
            {codeQ.isLoading && <p style={{ padding: 12, color: "#6b7280" }}>Loading code patch…</p>}
            {!codeQ.isLoading && activePatches.length === 0 && (
              <p style={{ padding: 12, color: "#6b7280", fontSize: 13 }}>
                No code patch available for this doc.
              </p>
            )}
            {activePatches.map(({ file, patch }) => (
              <PatchBlock key={file} file={file} patch={patch} />
            ))}
          </div>
        </section>

        <section style={paneShellStyle}>
          <header style={paneHeader("#831843", "#fdf2f8", "#ec4899")}>Documentation change</header>
          <div style={{ flex: 1, overflow: "auto", minHeight: 0 }}>
            {diffQ.isLoading && <p style={{ padding: 12, color: "#6b7280" }}>Loading doc diff…</p>}
            {!diffQ.isLoading && !activeDiff && (
              <p style={{ padding: 12, color: "#6b7280", fontSize: 13 }}>No doc diff for this artifact.</p>
            )}
            {activeDiff && <DocDiff diff={activeDiff} />}
          </div>
        </section>
      </div>
    </div>
  );
}

const paneShellStyle = {
  display: "flex",
  flexDirection: "column",
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  background: "#fff",
  overflow: "hidden",
  minHeight: 0,
};

function PatchBlock({ file, patch }) {
  const { before, after } = useMemo(() => splitPatch(patch), [patch]);
  return (
    <div style={{ borderTop: "1px solid #f3f4f6" }}>
      <div
        style={{
          padding: "6px 12px",
          background: "#f9fafb",
          fontSize: 12,
          color: "#374151",
          fontFamily: "ui-monospace, monospace",
          borderBottom: "1px solid #f3f4f6",
        }}
      >
        {file}
      </div>
      <ReactDiffViewer
        oldValue={before}
        newValue={after}
        splitView={false}
        useDarkTheme={false}
        showDiffOnly={true}
      />
    </div>
  );
}

function splitPatch(patch) {
  const before = [];
  const after = [];
  for (const line of (patch || "").split("\n")) {
    if (line.startsWith("@@") || line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("---") || line.startsWith("+++")) {
      continue;
    }
    if (line.startsWith("+")) {
      after.push(line.slice(1));
    } else if (line.startsWith("-")) {
      before.push(line.slice(1));
    } else {
      before.push(line.startsWith(" ") ? line.slice(1) : line);
      after.push(line.startsWith(" ") ? line.slice(1) : line);
    }
  }
  return { before: before.join("\n"), after: after.join("\n") };
}

function navBtnStyle(disabled) {
  return {
    padding: "4px 10px",
    borderRadius: 6,
    border: "1px solid #d1d5db",
    background: disabled ? "#f3f4f6" : "#fff",
    color: disabled ? "#9ca3af" : "#374151",
    cursor: disabled ? "not-allowed" : "pointer",
    fontSize: 13,
  };
}

function paneHeader(fg, bg, border) {
  return {
    padding: "8px 12px",
    background: bg,
    color: fg,
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: 0.3,
    textTransform: "uppercase",
    borderBottom: `1px solid ${border}`,
  };
}
