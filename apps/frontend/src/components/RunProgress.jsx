export function RunProgress({ run }) {
  if (!run) return null;
  const done = run.status === "succeeded";
  const failed = run.status === "failed";
  if (done) return null;
  const pct = Math.max(0, Math.min(100, Number(run.progress) || 0));
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "12px 24px",
        background: failed ? "var(--danger-soft)" : "var(--bg-subtle)",
        borderBottom: "1px solid var(--border)",
        fontSize: 13,
        position: "relative",
      }}
    >
      {!failed && <Spinner />}
      {failed && (
        <span
          style={{
            width: 18,
            height: 18,
            borderRadius: "50%",
            background: "var(--danger-soft)",
            color: "var(--danger)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 700,
            fontSize: 12,
            border: "1px solid color-mix(in srgb, var(--danger) 25%, transparent)",
          }}
        >
          !
        </span>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            fontWeight: 600,
            color: failed ? "var(--danger)" : "var(--fg)",
          }}
        >
          <span>{failed ? "Analysis failed" : "Agents at work"}</span>
          {!failed && (
            <span
              className="mono"
              style={{ color: "var(--fg-subtle)", fontWeight: 500, fontSize: 12 }}
            >
              {pct}%
            </span>
          )}
        </div>
        <div style={{ color: "var(--fg-subtle)", fontSize: 11, marginTop: 2 }}>
          stage:{" "}
          <span className="mono" style={{ color: "var(--fg-muted)" }}>
            {run.stage || "—"}
          </span>
          {run.error ? (
            <span style={{ color: "var(--danger)" }}> · {run.error}</span>
          ) : null}
        </div>
      </div>
      {!failed && (
        <div
          aria-hidden
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            height: 2,
            background: "var(--border)",
          }}
        >
          <div
            style={{
              width: `${pct}%`,
              height: "100%",
              background: "var(--fg)",
              transition: "width 600ms ease",
            }}
          />
        </div>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <div
      style={{
        width: 16,
        height: 16,
        border: "1.5px solid var(--border-strong)",
        borderTopColor: "var(--fg)",
        borderRadius: "50%",
        animation: "aura-spin 0.9s linear infinite",
      }}
    />
  );
}
