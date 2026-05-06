import { useEffect, useState } from "react";

const API = "http://localhost:8001/api/v1";

export function App() {
  const [session, setSession] = useState(false);
  const [loadingSession, setLoadingSession] = useState(true);
  const [repos, setRepos] = useState([]);
  const [repoId, setRepoId] = useState("");
  const [branch, setBranch] = useState("main");
  const [status, setStatus] = useState("Idle");
  const [run, setRun] = useState(null);

  const selectedRepo = repos.find((r) => r.id === repoId) || null;

  async function connectAuth() {
    const res = await fetch(`${API}/auth/github/start`, { credentials: "include" });
    if (!res.ok) {
      setStatus("GitHub OAuth not configured on backend.");
      return;
    }
    const data = await res.json();
    window.location.href = data.auth_url;
  }

  async function loadSession() {
    setLoadingSession(true);
    try {
      const res = await fetch(`${API}/auth/github/me`, { credentials: "include", cache: "no-store" });
      if (res.ok) {
        setSession(true);
        setStatus("Signed in.");
      } else if (res.status === 401) {
        setSession(false);
        setStatus("Sign in with GitHub to continue.");
      } else {
        setSession(false);
        setStatus("Unable to verify session.");
      }
    } catch {
      setSession(false);
      setStatus("Network error while verifying session.");
    } finally {
      setLoadingSession(false);
    }
  }

  async function loadRepos() {
    try {
      const res = await fetch(`${API}/github/repos/oauth`, {
        credentials: "include",
        cache: "no-store",
      });
      if (!res.ok) {
        if (res.status === 401) {
          setSession(false);
          setRepos([]);
          setRepoId("");
          setStatus("Session expired. Sign in again.");
          return;
        }
        let detail = "Failed to load repositories.";
        try {
          const err = await res.json();
          if (err?.detail) detail = String(err.detail);
        } catch {}
        setStatus(detail);
        return;
      }

      const data = await res.json();
      const rows = data.repos || [];
      setRepos(rows);
      if (rows.length > 0) {
        const keep = rows.some((r) => r.id === repoId);
        setRepoId(keep ? repoId : rows[0].id);
        setStatus(`Loaded ${rows.length} repositories.`);
      } else {
        setRepoId("");
        setStatus("No repositories found for this account.");
      }
    } catch {
      setStatus("Network error while loading repositories.");
    }
  }

  async function startAnalysis() {
    if (!repoId) return;
    const res = await fetch(`${API}/repos/analyze`, {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ github_repo_id: repoId, branch }),
    });
    if (!res.ok) {
      let detail = "Failed to queue analysis.";
      try {
        const err = await res.json();
        if (err?.detail) detail = String(err.detail);
      } catch {}
      setStatus(detail);
      return;
    }
    const data = await res.json();
    setRun(data);
    setStatus(`Run queued (#${data.run_id}).`);
  }

  useEffect(() => {
    (async () => {
      await loadSession();
    })();
  }, []);

  useEffect(() => {
    if (session) {
      loadRepos();
    }
  }, [session]);

  return (
    <div className="page">
      <h1>Aura</h1>
      <p className="muted">Select repository and branch.</p>

      {loadingSession ? (
        <div className="card">
          <p>Checking session...</p>
        </div>
      ) : !session ? (
        <div className="row">
          <button onClick={connectAuth}>Sign in with GitHub</button>
        </div>
      ) : (
        <div className="card">
          <div className="toolbar">
            <h3>Repository Selection</h3>
            <button onClick={loadRepos} title="Refresh repositories" aria-label="Refresh repositories">
              Refresh
            </button>
          </div>
          <div className="grid">
          <label>
            Repository
            <select value={repoId} onChange={(e) => setRepoId(e.target.value)} style={{ flex: 1 }}>
              <option value="">Select repository</option>
              {repos.map((r) => (
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
            <button onClick={startAnalysis} disabled={!repoId}>
              Analyze Repository
            </button>
          </div>
        </div>
      )}

      <p className="status">{status}</p>

      {selectedRepo && (
        <div className="card">
          <h3>Selection</h3>
          <p>Repository: {selectedRepo.full_name}</p>
          <p>Branch: {branch || "main"}</p>
          {run?.run_id && <p>Run ID: {run.run_id}</p>}
        </div>
      )}
    </div>
  );
}
