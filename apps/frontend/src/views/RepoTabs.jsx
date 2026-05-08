import { useEffect, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";

import { DocsDashboard } from "./DocsDashboard";
import { ImpactGraph } from "./ImpactGraph";
import { PrDiffView } from "./PrDiffView";
import { RepoPrsView } from "./RepoPrsView";
import { usePrImpact } from "../api";

/** Documentation tab — reuses DocsDashboard against the canonical run. */
export function RepoDocsTab() {
  const { canonicalRunId, repo } = useOutletContext();
  if (!canonicalRunId) {
    return (
      <div style={{ padding: 24, color: "#6b7280" }}>
        No documentation generated for {repo?.full_name || "this repo"} yet.
      </div>
    );
  }
  return <DocsDashboard runIdOverride={canonicalRunId} />;
}

/** Code graph tab — canonical graph (no PR overlay). */
export function RepoGraphTab() {
  const { canonicalRunId, repoId } = useOutletContext();
  if (!canonicalRunId) {
    return <div style={{ padding: 24, color: "#6b7280" }}>No graph yet — run analysis first.</div>;
  }
  return <ImpactGraph runIdOverride={canonicalRunId} repoIdOverride={repoId} />;
}

/** PRs list tab. */
export function RepoPrsTab() {
  return <RepoPrsView />;
}

/** PR detail — sub-tabs Documentation | Blast radius. */
export function RepoPrDetailTab() {
  const { pullRequestId } = useParams();
  const numericId = Number(pullRequestId);
  const { canonicalRunId, repoId } = useOutletContext();
  const impactQ = usePrImpact(numericId);
  const prRunId = impactQ.data?.pr_analysis_run_id;
  const subTab = useSubTab();

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div
        style={{
          padding: "8px 16px",
          background: "#f9fafb",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          gap: 6,
          flexShrink: 0,
        }}
      >
        <SubTabBtn active={subTab === "docs"} onClick={() => setSubTabHash("docs")}>
          📝 Documentation change
        </SubTabBtn>
        <SubTabBtn active={subTab === "blast"} onClick={() => setSubTabHash("blast")}>
          💥 Blast radius
        </SubTabBtn>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
        {subTab === "docs" && <PrDiffView pullRequestIdOverride={pullRequestId} />}
        {subTab === "blast" && (
          canonicalRunId ? (
            <ImpactGraph runIdOverride={canonicalRunId} repoIdOverride={repoId} prRunIdOverride={prRunId ? String(prRunId) : ""} />
          ) : (
            <div style={{ padding: 24, color: "#6b7280" }}>No canonical run to overlay.</div>
          )
        )}
      </div>
    </div>
  );
}

function SubTabBtn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "6px 12px",
        borderRadius: 6,
        border: "1px solid #d1d5db",
        background: active ? "#1f2937" : "#fff",
        color: active ? "#fff" : "#374151",
        cursor: "pointer",
        fontSize: 13,
        fontWeight: 600,
      }}
    >
      {children}
    </button>
  );
}

function useSubTab() {
  const [tab, setTab] = useState(() => {
    if (typeof window === "undefined") return "docs";
    return window.location.hash.replace(/^#/, "") === "blast" ? "blast" : "docs";
  });
  useEffect(() => {
    function onChange() {
      setTab(window.location.hash.replace(/^#/, "") === "blast" ? "blast" : "docs");
    }
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return tab;
}

function setSubTabHash(tab) {
  const url = new URL(window.location.href);
  url.hash = tab;
  window.history.replaceState({}, "", url.toString());
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}
