/**
 * Aura brand mark — friendly open-book glyph on a graphite tile,
 * with a sienna ribbon. Reads as "documentation, but warm."
 */
export function BrandMark({ size = 22, className }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      role="img"
      aria-label="Aura"
      className={className}
      style={{ flexShrink: 0 }}
    >
      <rect width="24" height="24" rx="6" fill="#18181b" />
      {/* left page */}
      <path
        d="M5.6 7.2 C 7.4 6.6, 9.6 6.6, 11.2 7.5 L 11.2 17.6 C 9.6 16.7, 7.4 16.7, 5.6 17.3 Z"
        fill="#ffffff"
      />
      {/* right page */}
      <path
        d="M18.4 7.2 C 16.6 6.6, 14.4 6.6, 12.8 7.5 L 12.8 17.6 C 14.4 16.7, 16.6 16.7, 18.4 17.3 Z"
        fill="#ffffff"
      />
      {/* spine */}
      <line
        x1="12"
        y1="7.4"
        x2="12"
        y2="17.4"
        stroke="#18181b"
        strokeWidth="0.6"
      />
      {/* sienna ribbon — bookmark, the friendly accent */}
      <path
        d="M14.7 7.0 L 14.7 12.4 L 13.7 11.5 L 12.7 12.4 L 12.7 7.2"
        fill="#8a3b1c"
      />
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

export function repoUrl(fullName) {
  if (!fullName) return null;
  return `https://github.com/${fullName}`;
}
