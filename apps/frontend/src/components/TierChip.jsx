const TIER_STYLES = {
  Direct: { bg: "#fee2e2", fg: "#b91c1c", border: "#fca5a5" },
  High: { bg: "#ffedd5", fg: "#c2410c", border: "#fdba74" },
  Medium: { bg: "#fef9c3", fg: "#854d0e", border: "#fde68a" },
};

/**
 * Tiny pill showing a change-impact tier for a doc-diff or graph node.
 * Color matches the graph node colors.
 */
export function TierChip({ tier, count }) {
  const style = TIER_STYLES[tier] || { bg: "#e5e7eb", fg: "#374151", border: "#d1d5db" };
  return (
    <span
      style={{
        padding: "2px 8px",
        borderRadius: 12,
        fontSize: 12,
        fontWeight: 600,
        color: style.fg,
        background: style.bg,
        border: `1px solid ${style.border}`,
        whiteSpace: "nowrap",
      }}
    >
      {tier}
      {count !== undefined ? ` · ${count}` : ""}
    </span>
  );
}

export const TIER_NODE_COLOR = {
  Direct: "#ef4444",
  High: "#f97316",
  Medium: "#eab308",
};
