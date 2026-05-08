/**
 * Renders a green "verified" pill for inline `[verified: file:Lstart-Lend]`
 * citations emitted by the writer agent. Hovering shows the exact line range.
 *
 * Used by ``DocsDashboard``'s react-markdown text-renderer override.
 */
export function VerifiedBadge({ path, start, end, repoFullName, headSha }) {
  const url =
    repoFullName && headSha
      ? `https://github.com/${repoFullName}/blob/${headSha}/${path}#L${start}-L${end}`
      : null;
  const label = `${path}:L${start}-L${end}`;
  const inner = (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "1px 7px 1px 5px",
        borderRadius: 999,
        fontSize: 11,
        fontFamily: "var(--font-mono)",
        fontWeight: 500,
        color: "#047857",
        background: "#ecfdf5",
        border: "1px solid #a7f3d0",
        marginLeft: 4,
        verticalAlign: "baseline",
        cursor: url ? "pointer" : "help",
        lineHeight: 1.4,
      }}
      title={`Verified by source: ${label}`}
    >
      <span
        aria-hidden
        style={{
          display: "inline-flex",
          width: 11,
          height: 11,
          borderRadius: "50%",
          background: "#10b981",
          color: "#fff",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 8,
          fontWeight: 700,
        }}
      >
        ✓
      </span>
      {path.split("/").pop()}:L{start}
    </span>
  );
  if (url) {
    return (
      <a href={url} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
        {inner}
      </a>
    );
  }
  return inner;
}
