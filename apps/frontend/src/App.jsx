import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { API, readErrorDetail } from "./api";
import { DocsScreen } from "./screens/DocsScreen";
import { SetupScreen } from "./screens/SetupScreen";

export function App() {
  const [session, setSession] = useState(false);
  const [loadingSession, setLoadingSession] = useState(true);
  const [repos, setRepos] = useState([]);
  const [repoId, setRepoId] = useState("");
  const [branch, setBranch] = useState("main");
  const [status, setStatus] = useState("Idle");
  const [run, setRun] = useState(null);

  const selectedRepo = repos.find((repo) => repo.id === repoId) || null;

  function expireSession(message) {
    setSession(false);
    setRepos([]);
    setRepoId("");
    setRun(null);
    setStatus(message);
  }

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
      const res = await fetch(`${API}/auth/github/me`, {
        credentials: "include",
        cache: "no-store",
      });

      if (res.ok) {
        setSession(true);
        setStatus("Signed in.");
      } else if (res.status === 401) {
        expireSession("Sign in with GitHub to continue.");
      } else {
        expireSession("Unable to verify session.");
      }
    } catch {
      expireSession("Network error while verifying session.");
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
          expireSession("Session expired. Sign in again.");
          return;
        }

        setStatus(await readErrorDetail(res, "Failed to load repositories."));
        return;
      }

      const data = await res.json();
      const rows = data.repos || [];
      setRepos(rows);

      if (rows.length > 0) {
        const keepSelected = rows.some((repo) => repo.id === repoId);
        setRepoId(keepSelected ? repoId : rows[0].id);
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
    if (!repoId) {
      return;
    }

    try {
      const res = await fetch(`${API}/repos/analyze`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ github_repo_id: repoId, branch }),
      });

      if (!res.ok) {
        if (res.status === 401) {
          expireSession("Session expired. Sign in again.");
          return;
        }

        setStatus(await readErrorDetail(res, "Failed to queue analysis."));
        return;
      }

      const data = await res.json();
      setRun(data);
      setStatus(`Run queued (#${data.run_id}). Open the docs reader once generation completes.`);
    } catch {
      setStatus("Network error while queueing analysis.");
    }
  }

  useEffect(() => {
    loadSession();
  }, []);

  useEffect(() => {
    if (session) {
      loadRepos();
    }
  }, [session]);

  return (
    <Routes>
      <Route
        path="/"
        element={
          <SetupScreen
            branch={branch}
            connectAuth={connectAuth}
            loadingSession={loadingSession}
            loadRepos={loadRepos}
            repoId={repoId}
            repos={repos}
            run={run}
            selectedRepo={selectedRepo}
            session={session}
            setBranch={setBranch}
            setRepoId={setRepoId}
            startAnalysis={startAnalysis}
            status={status}
          />
        }
      />
      <Route
        path="/repos/:repoId/docs"
        element={
          <DocsScreen
            connectAuth={connectAuth}
            loadingSession={loadingSession}
            onSessionExpired={expireSession}
            session={session}
          />
        }
      />
      <Route
        path="/repos/:repoId/docs/:sectionId"
        element={
          <DocsScreen
            connectAuth={connectAuth}
            loadingSession={loadingSession}
            onSessionExpired={expireSession}
            session={session}
          />
        }
      />
      <Route path="*" element={<Navigate replace to="/" />} />
    </Routes>
  );
}
