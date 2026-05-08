import { useEffect, useMemo } from "react";
import ReactDiffViewer from "react-diff-viewer-continued";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { useAffectedDocs, useCodeDiff, usePrDocDiff, usePrImpact } from "../api";
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

  return (
    <div style={{ padding: 16 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: 12,
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          marginBottom: 12,
          flexWrap: "wrap",
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
            marginBottom: 12,
            fontSize: 13,
          }}
        >
          ⚠ Documentation mismatch detected:{" "}
          {(mismatchFlags.undocumented_endpoint?.length || 0)} undocumented endpoint(s),{" "}
          {(mismatchFlags.undocumented_data_model?.length || 0)} undocumented data model(s),{" "}
          {(mismatchFlags.direct_or_high_doc_diff?.length || 0)} Direct/High doc diff(s).
        </div>
      )}

      {activeItem && (
        <div style={{ marginBottom: 8, fontSize: 12, color: "#6b7280" }}>
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

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignItems: "start" }}>
        <section
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            background: "#fff",
            overflow: "hidden",
            minHeight: 240,
          }}
        >
          <header style={paneHeader("#0c4a6e", "#e0f2fe", "#0284c7")}>Code change</header>
          {codeQ.isLoading && <p style={{ padding: 12, color: "#6b7280" }}>Loading code patch…</p>}
          {!codeQ.isLoading && activePatches.length === 0 && (
            <p style={{ padding: 12, color: "#6b7280", fontSize: 13 }}>
              No code patch available for this doc.
            </p>
          )}
          {activePatches.map(({ file, patch }) => (
            <PatchBlock key={file} file={file} patch={patch} />
          ))}
        </section>

        <section
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            background: "#fff",
            overflow: "hidden",
            minHeight: 240,
          }}
        >
          <header style={paneHeader("#831843", "#fdf2f8", "#ec4899")}>Documentation change</header>
          {diffQ.isLoading && <p style={{ padding: 12, color: "#6b7280" }}>Loading doc diff…</p>}
          {!diffQ.isLoading && !activeDiff && (
            <p style={{ padding: 12, color: "#6b7280", fontSize: 13 }}>No doc diff for this artifact.</p>
          )}
          {activeDiff && <DocDiff diff={activeDiff} />}
        </section>
      </div>

      {ordered.length > 0 && (
        <details style={{ marginTop: 18 }}>
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
    </div>
  );
}

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
