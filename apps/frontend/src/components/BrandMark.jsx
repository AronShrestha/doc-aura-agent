import { useMemo } from "react";

/**
 * Doc AURA brand mark — a parchment page floating inside a soft warm halo.
 * Carries the project's two ideas at once: "documentation" (the page with a
 * folded corner and ink lines) and "aura" (the radial glow behind it).
 * Tile-less so it sits cleanly on light or dark surfaces without harsh
 * black borders. Stroke colors are drawn from the warm cream/graphite
 * palette already used across the app.
 */
export function BrandMark({ size = 22, className }) {
  // Stable per-instance gradient ids so multiple <BrandMark> on a page
  // don't trample each other's <defs>.
  const uid = useMemo(() => `bm-${Math.random().toString(36).slice(2, 8)}`, []);
  const haloId = `${uid}-halo`;
  const pageId = `${uid}-page`;
  const inkId = `${uid}-ink`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label="Doc AURA"
      className={className}
      style={{ flexShrink: 0 }}
    >
      <defs>
        <radialGradient id={haloId} cx="50%" cy="48%" r="50%">
          <stop offset="0%" stopColor="#f5b870" stopOpacity="0.55" />
          <stop offset="55%" stopColor="#e89344" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#e89344" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={pageId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fffdf6" />
          <stop offset="100%" stopColor="#f3ead4" />
        </linearGradient>
        <linearGradient id={inkId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#3f3f46" />
          <stop offset="100%" stopColor="#71717a" />
        </linearGradient>
      </defs>

      {/* Aura — soft warm halo behind the page. */}
      <circle cx="16" cy="16" r="15.5" fill={`url(#${haloId})`} />

      {/* Page body with folded top-right corner. */}
      <path
        d="M7.6 8.4 a2.2 2.2 0 0 1 2.2 -2.2 h10.6 l5.4 5.4 v11.6 a2.2 2.2 0 0 1 -2.2 2.2 h-13.8 a2.2 2.2 0 0 1 -2.2 -2.2 z"
        fill={`url(#${pageId})`}
        stroke="#cbbf9d"
        strokeWidth="0.7"
      />
      {/* Fold shadow. */}
      <path
        d="M20.4 6.2 v3.6 a1.6 1.6 0 0 0 1.6 1.6 h3.8"
        fill="none"
        stroke="#cbbf9d"
        strokeWidth="0.7"
        strokeLinejoin="round"
      />
      {/* Fold flap. */}
      <path
        d="M20.4 6.2 l5.4 5.4 h-3.8 a1.6 1.6 0 0 1 -1.6 -1.6 z"
        fill="#e8dcb8"
      />

      {/* Ink lines — varied length for natural rhythm. */}
      <rect x="10.6" y="14.4" width="10.8" height="1.5" rx="0.75" fill={`url(#${inkId})`} />
      <rect x="10.6" y="17.4" width="10.8" height="1.5" rx="0.75" fill={`url(#${inkId})`} />
      <rect x="10.6" y="20.4" width="8" height="1.5" rx="0.75" fill={`url(#${inkId})`} opacity="0.85" />

      {/* "Aura" accent — small radiating dot at the page's leading edge. */}
      <circle cx="9" cy="9" r="1.3" fill="#b45309" />
      <circle cx="9" cy="9" r="2.6" fill="none" stroke="#b45309" strokeWidth="0.6" opacity="0.45" />
    </svg>
  );
}

export function GithubGlyph({ size = 14, className, color = "currentColor" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={color}
      role="img"
      aria-label="GitHub"
      className={className}
      style={{ flexShrink: 0 }}
    >
      <path d="M12 .5C5.7.5.6 5.6.6 12c0 5.1 3.3 9.4 7.8 10.9.6.1.8-.2.8-.6v-2.1c-3.2.7-3.8-1.4-3.8-1.4-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.7.4-1.3.7-1.5-2.5-.3-5.2-1.3-5.2-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2 1-.3 2-.4 3-.4s2 .1 3 .4c2.3-1.5 3.3-1.2 3.3-1.2.7 1.6.2 2.8.1 3.1.8.8 1.2 1.9 1.2 3.1 0 4.4-2.7 5.4-5.2 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.5-1.5 7.8-5.8 7.8-10.9C23.4 5.6 18.3.5 12 .5z" />
    </svg>
  );
}

/**
 * Document glyph — clean reconstruction of the user's reference image:
 * a sheet of paper with a folded top-right corner and four content lines.
 * Drawn entirely as crisp vector primitives (no raster grain or texture).
 */
export function DocsIcon({ size = 18, className, accent = "#5b7cf2", lineColor = "#ffffff" }) {
  const fold = accent;
  const foldDark = "#3f5fd1";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 40"
      fill="none"
      role="img"
      aria-label="Docs"
      className={className}
      style={{ flexShrink: 0, display: "block" }}
    >
      {/* Body of the page (folded top-right corner cut). */}
      <path
        d="M2 4 a3 3 0 0 1 3 -3 h17 l8 8 v26 a3 3 0 0 1 -3 3 h-22 a3 3 0 0 1 -3 -3 z"
        fill={accent}
      />
      {/* Inner shadow under the folded corner. */}
      <path
        d="M22 1 v6 a2 2 0 0 0 2 2 h6"
        fill={foldDark}
        opacity="0.55"
      />
      {/* Fold flap. */}
      <path d="M22 1 l8 8 h-6 a2 2 0 0 1 -2 -2 z" fill={fold} />
      {/* Four content lines — varying length for natural feel. */}
      <rect x="7" y="18" width="18" height="2.4" rx="1.2" fill={lineColor} />
      <rect x="7" y="22.5" width="18" height="2.4" rx="1.2" fill={lineColor} />
      <rect x="7" y="27" width="14" height="2.4" rx="1.2" fill={lineColor} />
      <rect x="7" y="31.5" width="11" height="2.4" rx="1.2" fill={lineColor} />
    </svg>
  );
}

export function repoUrl(fullName) {
  if (!fullName) return null;
  return `https://github.com/${fullName}`;
}
