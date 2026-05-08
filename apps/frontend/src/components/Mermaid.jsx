import { useCallback, useEffect, useId, useRef, useState } from "react";
import mermaid from "mermaid";

let initialized = false;
function ensureInit() {
  if (initialized) return;
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    suppressErrorRendering: true,
    theme: "base",
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
    themeVariables: {
      // High-contrast editorial palette: white surface, graphite ink,
      // strong borders, sienna accent for second-tier nodes.
      primaryColor: "#ffffff",
      primaryTextColor: "#0a0a0a",
      primaryBorderColor: "#18181b",
      lineColor: "#3f3f3f",
      secondaryColor: "#f6ece5",
      secondaryTextColor: "#3a1505",
      secondaryBorderColor: "#8a3b1c",
      tertiaryColor: "#f0efea",
      tertiaryTextColor: "#0a0a0a",
      tertiaryBorderColor: "#4a4a4a",
      noteBkgColor: "#fef3c7",
      noteBorderColor: "#92400e",
      noteTextColor: "#3a1d05",
      clusterBkg: "#f7f7f4",
      clusterBorder: "#4a4a4a",
      edgeLabelBackground: "#ffffff",
      mainBkg: "#ffffff",
      nodeBorder: "#18181b",
      titleColor: "#0a0a0a",
      fontSize: "14px",
    },
    themeCSS: `
      .node rect, .node polygon, .node circle, .node ellipse, .node path {
        stroke-width: 1.6px !important;
      }
      .node .label, .nodeLabel, .edgeLabel {
        font-weight: 500 !important;
        color: #0a0a0a !important;
      }
      .edgeLabel { background-color: #ffffff !important; padding: 2px 4px; }
      .edgePath path, .flowchart-link {
        stroke-width: 1.5px !important;
      }
      .cluster rect { stroke-width: 1.4px !important; }
      .messageLine0, .messageLine1 { stroke-width: 1.6px !important; }
      .actor { stroke-width: 1.6px !important; }
      .marker { fill: #3f3f3f !important; stroke: #3f3f3f !important; }
    `,
    flowchart: { htmlLabels: true, curve: "basis", padding: 14 },
    sequence: { actorMargin: 50, useMaxWidth: true },
    er: { useMaxWidth: true },
  });
  initialized = true;
}

function scrubOrphans(renderId) {
  for (const sel of [`#${renderId}`, `#d${renderId}`]) {
    document.querySelectorAll(sel).forEach((el) => el.remove());
  }
}

function isEffectivelyEmptySource(src) {
  if (!src) return true;
  const lines = src
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("%%"));
  // First line is the diagram type declaration (e.g. "graph LR").
  // If nothing meaningful follows it, the diagram has no content.
  return lines.length <= 1;
}

function svgHasContent(svg) {
  if (!svg) return false;
  // Mermaid emits node/actor/state/entity classes for renderables.
  return /class="[^"]*\b(node|actor|er entityBox|state-group|classGroup|requirementBox|task|section)\b/.test(svg);
}

// LLMs sometimes emit Unicode arrows / smart quotes / fancy dashes that
// mermaid can't parse. Normalize the most common cases so a borderline-valid
// diagram renders instead of failing.
function sanitizeMermaidSource(src) {
  if (!src) return "";
  let out = src;
  // Strip leading "mermaid" word if a generator prepended it as a header.
  out = out.replace(/^\s*mermaid\s*\n/i, "");
  // Strip code-fence remnants if any escaped through.
  out = out.replace(/^\s*```(?:mermaid)?\s*\n/i, "").replace(/\n```\s*$/i, "");
  // Smart quotes → straight quotes.
  out = out.replace(/[‘’‚‛]/g, "'").replace(/[“”„‟]/g, '"');
  // Ellipsis → three dots.
  out = out.replace(/…/g, "...");
  // Bidirectional arrows.
  out = out.replace(/[↔⟷]/g, "<-->");
  // Right arrows (single & double, long & short, heavy variants) → -->.
  out = out.replace(/[→➜➝➞➟➡⭢⟶⇾↪]/g, "-->");
  out = out.replace(/[⇒⟹⭲]/g, "==>");
  // Left arrows → <--.
  out = out.replace(/[←⟵⇐⟸]/g, "<--");
  // Replace stray non-breaking spaces with normal spaces.
  out = out.replace(/ /g, " ");
  return out;
}

export function Mermaid({ source }) {
  const id = useId().replace(/[:]/g, "_");
  const ref = useRef(null);
  const [svg, setSvg] = useState("");
  const [hidden, setHidden] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    ensureInit();
    let cancelled = false;
    setHidden(false);
    const renderId = `mmd-${id}`;

    const cleaned = sanitizeMermaidSource(source);

    if (isEffectivelyEmptySource(cleaned)) {
      setHidden(true);
      return;
    }

    (async () => {
      try {
        const ok = await mermaid.parse(cleaned, { suppressErrors: true });
        if (ok === false) {
          if (!cancelled) setHidden(true);
          scrubOrphans(renderId);
          return;
        }
        const result = await mermaid.render(renderId, cleaned);
        if (cancelled) return;
        if (!svgHasContent(result.svg)) {
          setHidden(true);
          return;
        }
        setSvg(result.svg);
        if (ref.current) ref.current.innerHTML = result.svg;
      } catch (_e) {
        if (!cancelled) setHidden(true);
        scrubOrphans(renderId);
      }
    })();

    return () => {
      cancelled = true;
      scrubOrphans(renderId);
    };
  }, [source, id]);

  if (hidden) return null;

  return (
    <>
      <div
        ref={ref}
        className="mermaid-block"
        role="button"
        tabIndex={0}
        title="Click to expand"
        onClick={() => svg && setExpanded(true)}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && svg) {
            e.preventDefault();
            setExpanded(true);
          }
        }}
        style={{
          margin: "20px 0",
          padding: "20px",
          background: "var(--bg-subtle)",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius)",
          textAlign: "center",
          overflowX: "auto",
        }}
      />
      {expanded && (
        <MermaidOverlay svg={svg} onClose={() => setExpanded(false)} />
      )}
    </>
  );
}

function MermaidOverlay({ svg, onClose }) {
  const stageRef = useRef(null);
  const [scale, setScale] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const dragRef = useRef({ active: false, startX: 0, startY: 0, originTx: 0, originTy: 0 });

  // Esc to close + lock body scroll while open.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "0") reset();
      if (e.key === "+" || e.key === "=") setScale((s) => clampScale(s * 1.2));
      if (e.key === "-" || e.key === "_") setScale((s) => clampScale(s / 1.2));
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  const reset = useCallback(() => {
    setScale(1);
    setTx(0);
    setTy(0);
  }, []);

  const onWheel = useCallback((e) => {
    e.preventDefault();
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect) return;
    const cx = e.clientX - rect.left - rect.width / 2;
    const cy = e.clientY - rect.top - rect.height / 2;
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    setScale((s) => {
      const next = clampScale(s * factor);
      const k = next / s;
      // Zoom around cursor: shift translation so the point under the cursor
      // stays under the cursor after scaling.
      setTx((t) => cx - (cx - t) * k);
      setTy((t) => cy - (cy - t) * k);
      return next;
    });
  }, []);

  const onMouseDown = (e) => {
    if (e.button !== 0) return;
    dragRef.current = {
      active: true,
      startX: e.clientX,
      startY: e.clientY,
      originTx: tx,
      originTy: ty,
    };
  };

  const onMouseMove = (e) => {
    if (!dragRef.current.active) return;
    setTx(dragRef.current.originTx + (e.clientX - dragRef.current.startX));
    setTy(dragRef.current.originTy + (e.clientY - dragRef.current.startY));
  };

  const endDrag = () => {
    dragRef.current.active = false;
  };

  return (
    <div
      className="mermaid-overlay"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <button
        className="mermaid-overlay-close"
        onClick={onClose}
        aria-label="Close diagram"
        title="Close (Esc)"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>

      <div className="mermaid-overlay-toolbar">
        <button onClick={() => setScale((s) => clampScale(s / 1.2))} title="Zoom out (-)">−</button>
        <span className="mermaid-overlay-scale">{Math.round(scale * 100)}%</span>
        <button onClick={() => setScale((s) => clampScale(s * 1.2))} title="Zoom in (+)">+</button>
        <button onClick={reset} title="Reset (0)" className="mermaid-overlay-reset">reset</button>
      </div>

      <div
        ref={stageRef}
        className="mermaid-overlay-stage"
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={endDrag}
        onMouseLeave={endDrag}
        style={{ cursor: dragRef.current.active ? "grabbing" : "grab" }}
      >
        <div
          className="mermaid-overlay-zoom"
          style={{
            transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
          }}
        >
          <div
            className="mermaid-overlay-zoom-panel"
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </div>
      </div>

      <div className="mermaid-overlay-hint">
        scroll to zoom · drag to pan · esc to close
      </div>
    </div>
  );
}

function clampScale(s) {
  return Math.min(8, Math.max(0.2, s));
}
