import { useMemo } from "react";
import { Link, NavLink, Navigate, Outlet, useParams } from "react-router-dom";

import { useMyRepos } from "../api";

/**
 * /repos/:repoId/* — three-tab shell for a single repo:
 *   - Documentation  → /repos/:id/docs
 *   - Code Graph     → /repos/:id/graph
 *   - Pull requests  → /repos/:id/prs
 *
 * Renders <Outlet/>; each tab content lives in its own component.
 */
export function RepoLayout() {
  const { repoId } = useParams();
  const reposQ = useMyRepos();
  const repo = useMemo(
    () => (reposQ.data?.repos || []).find((r) => String(r.repo_id) === String(repoId)),
    [reposQ.data, repoId]
  );
  const canonicalRunId = repo?.latest_run?.id;

  return (
    <div style={{ minHeight: "calc(100vh - 56px)", display: "flex", flexDirection: "column" }}>
      <header
        style={{
          padding: "10px 16px",
          background: "#fff",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          alignItems: "center",
          gap: 16,
        }}
      >
        <Link
          to="/"
          style={{
            fontSize: 13,
            color: "#6b7280",
            textDecoration: "none",
            padding: "4px 10px",
            borderRadius: 999,
            border: "1px solid #e5e7eb",
            background: "#f9fafb",
          }}
        >
          ← Library
        </Link>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <strong style={{ fontSize: 15 }}>{repo?.full_name || "Repository"}</strong>
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            <span style={{ fontFamily: "ui-monospace, monospace" }}>{repo?.default_branch || ""}</span>
            {repo?.latest_run?.id ? (
              <>
                {" · canonical run #"}
                <span style={{ fontFamily: "ui-monospace, monospace" }}>{repo.latest_run.id}</span>
              </>
            ) : null}
          </span>
        </div>
        <nav style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          <Tab to={`/repos/${repoId}/docs`} label="Documentation" />
          <Tab to={`/repos/${repoId}/graph`} label="Code Graph" />
          <Tab to={`/repos/${repoId}/prs`} label="Pull requests" />
        </nav>
      </header>
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {!repo && reposQ.isFetched ? (
          <div style={{ padding: 24, color: "#6b7280" }}>Repository not found.</div>
        ) : (
          <Outlet context={{ repo, canonicalRunId, repoId: Number(repoId) }} />
        )}
      </div>
    </div>
  );
}

function Tab({ to, label }) {
  return (
    <NavLink
      to={to}
      end={false}
      style={({ isActive }) => ({
        padding: "6px 14px",
        borderRadius: 8,
        fontSize: 13,
        fontWeight: 600,
        textDecoration: "none",
        color: isActive ? "#fff" : "#374151",
        background: isActive ? "#1f2937" : "#fff",
        border: "1px solid #e5e7eb",
      })}
    >
      {label}
    </NavLink>
  );
}

/** /repos/:id (no sub-path) → redirect to /repos/:id/docs */
export function RepoIndexRedirect() {
  const { repoId } = useParams();
  return <Navigate to={`/repos/${repoId}/docs`} replace />;
}
