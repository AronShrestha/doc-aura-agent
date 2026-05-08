import { Link } from "react-router-dom";

import { BrandMark } from "../components/BrandMark";

const FEATURES = [
  {
    title: "Agents that read your repository",
    body: "Planner, extractor, and writer agents collaborate to build a verified, structured doc tree.",
  },
  {
    title: "Reviewer agents on every PR",
    body: "When a PR merges, agents diff the impact and update the affected docs automatically.",
  },
  {
    title: "Citations grounded in source",
    body: "Every paragraph links back to the exact file and line range that produced it.",
  },
];

const AGENTS = [
  { name: "planner", task: "scoping repository surface", status: "running" },
  { name: "extractor", task: "parsing 248 symbols", status: "running" },
  { name: "writer", task: "drafting architecture overview", status: "queued" },
  { name: "reviewer", task: "watching for PR merges", status: "idle" },
];

export function AuthLayout({ eyebrow, title, subtitle, children, footerSwitch }) {
  return (
    <div className="auth-shell">
      <aside className="auth-form-side">
        <Link to="/" className="auth-brand-row">
          <BrandMark size={26} />
          <span>Aura</span>
        </Link>

        <div className="auth-form-inner">
          {eyebrow && <div className="auth-eyebrow">{eyebrow}</div>}
          <h1 className="auth-title">{title}</h1>
          {subtitle && <p className="auth-sub">{subtitle}</p>}
          {children}
          {footerSwitch && <p className="auth-switch">{footerSwitch}</p>}
        </div>

        <div className="auth-footer">
          <span>© {new Date().getFullYear()} Aura</span>
          <span>
            <a href="#" onClick={(e) => e.preventDefault()}>Privacy</a>
            {" · "}
            <a href="#" onClick={(e) => e.preventDefault()}>Terms</a>
          </span>
        </div>
      </aside>

      <aside className="auth-brand-side" aria-hidden>
        <div className="auth-brand-top">
          <BrandMark size={26} />
          <span>Aura</span>
        </div>

        <div className="auth-quote">
          <h2>
            Documentation written by agents.
            <br />
            <em>Kept in sync, on every merge.</em>
          </h2>
          <p>
            Aura runs a team of agents over your codebase. They plan, extract, write, and verify —
            then review every pull request and rewrite the docs that change.
          </p>

          <ul className="auth-feature-list">
            {FEATURES.map((f) => (
              <li key={f.title} className="auth-feature">
                <span className="auth-feature-dot" aria-hidden />
                <span>
                  <strong>{f.title}</strong>
                  <br />
                  <span style={{ color: "#a1a1aa" }}>{f.body}</span>
                </span>
              </li>
            ))}
          </ul>

          <div className="auth-agents" role="img" aria-label="Agent activity preview">
            <div className="auth-agents-head">
              <span>Agent activity</span>
              <span className="auth-pulse">
                <span className="auth-pulse-dot" />
                live
              </span>
            </div>
            {AGENTS.map((a) => (
              <div key={a.name} className="auth-agent-row">
                <span className="auth-agent-name">{a.name}</span>
                <span className="auth-agent-task">{a.task}</span>
                <span
                  className={
                    "auth-agent-status " +
                    (a.status === "running" ? "is-running" : "is-done")
                  }
                >
                  {a.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="auth-foot-meta">
          <span>Multi-agent documentation engine</span>
          <span>
            <kbd>⌘</kbd> <kbd>K</kbd> to search docs once signed in
          </span>
        </div>
      </aside>
    </div>
  );
}
