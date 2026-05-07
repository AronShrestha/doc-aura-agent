import { Link } from "react-router-dom";

export function SetupScreen({
  branch,
  connectAuth,
  loadingSession,
  loadRepos,
  repoId,
  repos,
  run,
  selectedRepo,
  session,
  setBranch,
  setRepoId,
  startAnalysis,
  status,
}) {
  const docsHref = run?.repo_id ? `/repos/${run.repo_id}/docs` : null;

  return (
    <div className="page">
      <header className="hero">
        <div>
          <h1>Aura</h1>
          <p className="muted">Select a repository, queue analysis, then open the generated docs.</p>
        </div>
        {docsHref ? (
          <Link className="button-link secondary-button" to={docsHref}>
            Open Docs
          </Link>
        ) : null}
      </header>

      {loadingSession ? (
        <div className="card">
          <p>Checking session...</p>
        </div>
      ) : !session ? (
        <div className="card">
          <p>Sign in with GitHub to load repositories and generate docs.</p>
          <div className="row">
            <button type="button" onClick={connectAuth}>
              Sign in with GitHub
            </button>
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="toolbar">
            <div>
              <h3>Repository Selection</h3>
              <p className="muted compact">The docs reader uses the analyzed repo record returned by the backend.</p>
            </div>
            <button
              type="button"
              onClick={loadRepos}
              title="Refresh repositories"
              aria-label="Refresh repositories"
            >
              Refresh
            </button>
          </div>

          <div className="grid">
            <label>
              Repository
              <select value={repoId} onChange={(event) => setRepoId(event.target.value)}>
                <option value="">Select repository</option>
                {repos.map((repo) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.full_name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Branch
              <input
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
                placeholder="main"
              />
            </label>
          </div>

          <div className="row">
            <button type="button" onClick={startAnalysis} disabled={!repoId}>
              Analyze Repository
            </button>
            {docsHref ? (
              <Link className="button-link ghost-button" to={docsHref}>
                Browse Current Docs
              </Link>
            ) : null}
          </div>
        </div>
      )}

      <p className="status">{status}</p>

      {selectedRepo ? (
        <div className="card">
          <h3>Selection</h3>
          <p>Repository: {selectedRepo.full_name}</p>
          <p>Branch: {branch || "main"}</p>
          {run?.run_id ? <p>Latest queued run: #{run.run_id}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
