import { useMemo } from "react";

const KIND_LABEL = {
  stage: "stage",
  writer: "writer",
  narration: "agent",
};

export function AgentActivity({ activity, run }) {
  const items = useMemo(() => {
    const list = Array.isArray(activity) ? activity : [];
    // Newest first.
    return list.slice().reverse();
  }, [activity]);

  const isRunning = run && !["succeeded", "failed"].includes(run.status);

  if (items.length === 0) {
    return (
      <div className="activity-empty">
        <div className="activity-empty-bullet" />
        Waiting for the first agent to report in…
      </div>
    );
  }

  return (
    <div className="activity-feed">
      <header className="activity-feed-head">
        <span className="eyebrow">Agent activity</span>
        {isRunning ? (
          <span className="activity-live">
            <span className="activity-live-dot" />
            live
          </span>
        ) : (
          <span className="activity-done">complete</span>
        )}
      </header>
      <ol className="activity-list">
        {items.map((item, idx) => (
          <li
            key={`${item.ts}-${idx}`}
            className={`activity-row activity-kind-${item.kind || "stage"}`}
          >
            <span className="activity-time mono">{formatTime(item.ts)}</span>
            <span className="activity-kind">{KIND_LABEL[item.kind] || "agent"}</span>
            <span className="activity-msg">{item.message}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function formatTime(ts) {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "—";
  }
}
