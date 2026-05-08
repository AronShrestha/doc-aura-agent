import { useNavigate, useParams } from "react-router-dom";

import { useRepoPullRequests } from "../api";
import { TierChip } from "../components/TierChip";

/**
 * /repos/:repoId/prs — list active PRs for a repo. Click a row → /prs/:id
 * for the immersive code↔doc diff view.
 */
export function RepoPrsView() {
  const { repoId } = useParams();
  const navigate = useNavigate();
  const numericRepoId = Number(repoId);
  const prsQ = useRepoPullRequests(numericRepoId);
  const items = prsQ.data?.pull_requests || [];

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Active pull requests</h2>
        <span style={{ color: "#6b7280", fontSize: 13 }}>
          {items.length} PR{items.length === 1 ? "" : "s"}
        </span>
      </div>

      {prsQ.isLoading && <p>Loading…</p>}
      {!prsQ.isLoading && items.length === 0 && (
        <div
          style={{
            padding: 24,
            background: "#f9fafb",
            border: "1px dashed #e5e7eb",
            borderRadius: 8,
            color: "#6b7280",
          }}
        >
          No pull requests yet. Open a PR against this repo and Aura will analyze it.
        </div>
      )}

      <div style={{ display: "grid", gap: 8 }}>
        {items.map((pr) => {
          const run = pr.latest_pr_run;
          const tc = run?.tier_counts || {};
          return (
            <article
              key={pr.id}
              onClick={() => navigate(`/repos/${repoId}/prs/${pr.id}`)}
              role="link"
              tabIndex={0}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && navigate(`/repos/${repoId}/prs/${pr.id}`)}
              style={{
                padding: 14,
                border: "1px solid #e5e7eb",
                borderRadius: 10,
                background: "#fff",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 12,
              }}
            >
              <div style={{ minWidth: 60, fontWeight: 700, color: "#1f2937" }}>#{pr.number}</div>
              <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
                <div
                  style={{
                    fontWeight: 600,
                    color: "#111827",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <span>{pr.title || "(no title)"}</span>
                  {pr.html_url && (
                    <a
                      href={pr.html_url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      title="Open on GitHub"
                      style={{ fontSize: 11, color: "#6b7280", textDecoration: "none", border: "1px solid #e5e7eb", padding: "1px 6px", borderRadius: 999 }}
                    >
                      ↗ GitHub
                    </a>
                  )}
                  {pr.merged && (
                    <span style={{ fontSize: 11, color: "#581c87", background: "#faf5ff", border: "1px solid #d8b4fe", padding: "1px 6px", borderRadius: 999 }}>
                      merged
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 12, color: "#6b7280" }}>
                  <span style={{ fontFamily: "ui-monospace, monospace" }}>
                    {pr.base_ref} ← {pr.head_ref}
                  </span>
                  {" · "}
                  <span>{pr.state}</span>
                  {run?.updated_at && (
                    <>
                      {" · "}
                      <span>analyzed {new Date(run.updated_at).toLocaleString()}</span>
                    </>
                  )}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <TierChip tier="Direct" count={tc.Direct || 0} />
                <TierChip tier="High" count={tc.High || 0} />
                <TierChip tier="Medium" count={tc.Medium || 0} />
                {run?.has_mismatch && (
                  <span
                    title={`${run.mismatch_flag_count} mismatch flag(s)`}
                    style={{
                      padding: "2px 8px",
                      borderRadius: 12,
                      fontSize: 12,
                      fontWeight: 600,
                      color: "#7c2d12",
                      background: "#fef3c7",
                      border: "1px solid #fcd34d",
                    }}
                  >
                    ⚠ Mismatch
                  </span>
                )}
                {run?.status && run.status !== "succeeded" && (
                  <span style={{ fontSize: 11, color: "#6b7280" }}>{run.status}</span>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
