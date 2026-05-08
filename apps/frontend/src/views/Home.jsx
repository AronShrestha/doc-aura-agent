import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { client, useMe, useMyRepos } from "../api";
import { useAuth } from "../auth";
import { GithubGlyph, repoUrl } from "../components/BrandMark";

export function Home() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const meQuery = useMe();
  const reposQuery = useMyRepos();

  const me = meQuery.data;
  const githubLinked = !!me?.github_linked;
  const myRepos = reposQuery.data?.repos || [];

  const [ghRepos, setGhRepos] = useState([]);
  const [repoId, setRepoId] = useState("");
  const [branch, setBranch] = useState("main");
  const [status, setStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (searchParams.get("github_linked") === "1") {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      setStatus("GitHub connected.");
      const next = new URLSearchParams(searchParams);
      next.delete("github_linked");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams, queryClient]);

  useEffect(() => {
    if (githubLinked) loadGithubRepos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [githubLinked]);

  async function loadGithubRepos() {
    try {
      const { data } = await client.get("/github/repos/oauth");
      const rows = data.repos || [];
      setGhRepos(rows);
      if (rows.length > 0) {
        setRepoId((prev) => (rows.some((r) => r.id === prev) ? prev : rows[0].id));
      } else {
        setStatus("No repositories returned by GitHub.");
      }
    } catch (err) {
      if (err?.response?.status !== 401) {
        setStatus("Failed to load GitHub repositories.");
      }
    }
  }

  async function connectGithub() {
    try {
      const { data } = await client.get("/auth/github/start");
      window.location.href = data.auth_url;
    } catch {
      setStatus("GitHub OAuth not configured on backend.");
    }
  }

  async function startAnalysis() {
    if (!repoId) return;
    setSubmitting(true);
    setStatus("");
    try {
      const { data } = await client.post("/repos/analyze", {
        github_repo_id: repoId,
        branch,
      });
      queryClient.invalidateQueries({ queryKey: ["my-repos"] });
      navigate(`/runs/${data.run_id}`);
    } catch (err) {
      setStatus(err?.response?.data?.detail || "Failed to queue analysis.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <header className="home-hero">
        <div className="eyebrow">Aura · Living documentation</div>
        <h1 className="home-title">
          {user?.display_name ? `Welcome back, ${user.display_name}.` : "Documentation, written by agents."}
        </h1>
        <p className="home-lede">
          Each repository links to one evolving documentation set. Aura's agents read your code,
          write the docs, and rewrite them when a pull request changes the truth.
        </p>
      </header>

      <section className="home-section">
        <div className="section-head">
          <h2>Your library</h2>
          <span className="subtle">{myRepos.length} {myRepos.length === 1 ? "volume" : "volumes"}</span>
        </div>
        {reposQuery.isLoading ? (
          <div className="empty-card">Loading…</div>
        ) : myRepos.length === 0 ? (
          <div className="empty-card">
            <div className="empty-card-icon" aria-hidden>§</div>
            <div>
              <strong>No documentation yet.</strong>
              <div className="subtle" style={{ marginTop: 4 }}>
                Connect a repository below and the agents will start drafting.
              </div>
            </div>
          </div>
        ) : (
          <div className="repo-grid">
            {myRepos.map((r) => (
              <RepoCard key={r.repo_id} repo={r} />
            ))}
          </div>
        )}
      </section>

      <section className="home-section">
        <div className="section-head">
          <h2>Analyze a repository</h2>
        </div>
        {!githubLinked ? (
          <div className="card">
            <h3>Connect GitHub</h3>
            <p className="muted" style={{ marginTop: 0 }}>
              Aura needs read access to your repositories so the agents can analyze them.
            </p>
            <div className="row">
              <button className="primary" onClick={connectGithub}>
                Connect GitHub →
              </button>
            </div>
          </div>
        ) : (
          <div className="card">
            <div className="toolbar">
              <h3>Pick a repository</h3>
              <button className="ghost" onClick={loadGithubRepos}>↻ Refresh</button>
            </div>
            <div className="grid">
              <label>
                Repository
                <select value={repoId} onChange={(e) => setRepoId(e.target.value)}>
                  <option value="">Select repository</option>
                  {ghRepos.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Branch
                <input value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" />
              </label>
            </div>
            <div className="row">
              <button className="primary" onClick={startAnalysis} disabled={!repoId || submitting}>
                {submitting ? "Dispatching agents…" : "Dispatch agents"}
              </button>
            </div>
          </div>
        )}
        {status && <p className="status">{status}</p>}
      </section>
    </div>
  );
}

function RepoCard({ repo }) {
  const navigate = useNavigate();
  const run = repo.latest_run;
  const status = run?.status || "none";
  const stage = run?.stage || "";
  const progress = run?.progress ?? 0;
  const ready = status === "succeeded";
  const failed = status === "failed";
  const inFlight = run && !ready && !failed;
  const navigable = !!run?.id;

  const onCardClick = () => {
    if (navigable) navigate(`/runs/${run.id}`);
  };
  const onCardKey = (e) => {
    if (!navigable) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      navigate(`/runs/${run.id}`);
    }
  };

  return (
    <article
      className={`repo-card card ${navigable ? "card-hoverable repo-card-link" : ""}`}
      role={navigable ? "link" : undefined}
      tabIndex={navigable ? 0 : -1}
      onClick={navigable ? onCardClick : undefined}
      onKeyDown={navigable ? onCardKey : undefined}
    >
      <header className="repo-card-head">
        <div className="repo-card-title">
          <div className="repo-card-name">{repo.full_name}</div>
          <div className="subtle repo-card-branch">
            <span className="mono">{repo.default_branch || "main"}</span>
          </div>
        </div>
        <StatusBadge status={status} />
      </header>
      <div className="repo-card-meta">
        {run ? (
          <>
            <span className="mono">#{run.id}</span>
            {stage && <span className="repo-card-meta-sep">·</span>}
            {stage && <span>{stage}</span>}
            {inFlight && <span className="repo-card-meta-sep">·</span>}
            {inFlight && <span>{progress}%</span>}
          </>
        ) : (
          <span>Awaiting first analysis</span>
        )}
      </div>
      {inFlight && run?.last_message && (
        <div className="repo-card-narration">{run.last_message}</div>
      )}
      {inFlight && (
        <div className="repo-progress" aria-hidden>
          <div className="repo-progress-fill" style={{ width: `${progress}%` }} />
        </div>
      )}
      {repo.full_name && (
        <a
          className="repo-link repo-link-card"
          href={repoUrl(repo.full_name)}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          title={`Open ${repo.full_name} on GitHub`}
        >
          <GithubGlyph size={12} />
          <span>Open on GitHub</span>
        </a>
      )}
    </article>
  );
}

function StatusBadge({ status }) {
  const map = {
    succeeded: { tone: "ready", label: "Ready" },
    failed: { tone: "failed", label: "Failed" },
    running: { tone: "live", label: "Running" },
    queued: { tone: "queued", label: "Queued" },
    none: { tone: "idle", label: "Idle" },
  };
  const s = map[status] || map.running;
  return <span className={`status-pill is-${s.tone}`}>{s.label}</span>;
}
