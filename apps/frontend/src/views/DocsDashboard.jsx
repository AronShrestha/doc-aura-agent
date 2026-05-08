import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useQueryClient } from "@tanstack/react-query";

import { reAnalyzeRepoDocs, useDoc, useDocs, useRun } from "../api";
import { VerifiedBadge } from "../components/VerifiedBadge";
import { RunProgress } from "../components/RunProgress";
import { Mermaid } from "../components/Mermaid";
import { AgentActivity } from "../components/AgentActivity";
import { DocsIcon, GithubGlyph, repoUrl } from "../components/BrandMark";
import { DocChat } from "../components/DocChat";

/**
 * /runs/:runId — left rail of project-level docs rendered as a hierarchical
 * tree (folders match the slug path under .aura/docs/), right pane with the
 * full Markdown rendering. Inline `[verified: ...]` markers are rewritten
 * into VerifiedBadge pills.
 */
export function DocsDashboard({ runIdOverride } = {}) {
  const params = useParams();
  const runId = runIdOverride ?? params.runId;
  const numericRunId = Number(runId);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const runQ = useRun(numericRunId);
  const repoId = runQ.data?.repo_id;
  const docsQ = useDocs(repoId);
  const prevStatusRef = useRef(null);
  const [reAnalyzing, setReAnalyzing] = useState(false);

  async function handleReAnalyzeDocs() {
    if (!repoId || reAnalyzing) return;
    setReAnalyzing(true);
    try {
      const { run_id } = await reAnalyzeRepoDocs(repoId);
      queryClient.invalidateQueries({ queryKey: ["my-repos"] });
      navigate(`/runs/${run_id}`);
    } catch (err) {
      console.error("re-analyze docs failed", err);
    } finally {
      setReAnalyzing(false);
    }
  }

  // When the run transitions into a terminal state, force-refetch docs index
  // + active doc so the UI swaps from activity feed → real documentation
  // without requiring a manual page refresh.
  useEffect(() => {
    const status = runQ.data?.status;
    const prev = prevStatusRef.current;
    prevStatusRef.current = status;
    if (!status || prev === status) return;
    if (status === "succeeded" || status === "failed") {
      if (repoId) {
        queryClient.invalidateQueries({ queryKey: ["docs", repoId] });
        queryClient.invalidateQueries({ queryKey: ["doc", repoId] });
        queryClient.invalidateQueries({ queryKey: ["graph", repoId] });
      }
      queryClient.invalidateQueries({ queryKey: ["my-repos"] });
    }
  }, [runQ.data?.status, repoId, queryClient]);
  const indexData = docsQ.data;
  const sections = indexData?.sections || [];
  const manifestTree = indexData?.manifest_tree;
  const profile = indexData?.codebase_profile || {};
  const tree = useMemo(
    () => (manifestTree && manifestTree.length ? manifestTree : buildTreeFromSections(sections)),
    [manifestTree, sections]
  );
  const sectionByPath = useMemo(() => {
    const m = {};
    for (const s of sections) m[s.slug_path] = s;
    return m;
  }, [sections]);
  const sectionById = useMemo(() => {
    const m = {};
    for (const s of sections) m[s.section_id] = s;
    return m;
  }, [sections]);
  const [activeId, setActiveId] = useState(null);
  const [search, setSearch] = useState("");
  const [chatOpen, setChatOpen] = useState(true);
  const docQ = useDoc(repoId, activeId);

  // Auto-select first available doc once sections load.
  useEffect(() => {
    if (!activeId && sections.length) {
      setActiveId(sections[0].section_id);
    }
  }, [sections, activeId]);

  const filteredTree = useMemo(
    () => (search.trim() ? filterTree(tree, search.trim().toLowerCase(), sectionByPath) : tree),
    [tree, search, sectionByPath]
  );

  const run = runQ.data;
  const running = run && run.status !== "succeeded" && run.status !== "failed";
  const activeSection = activeId ? sectionById[activeId] : null;

  return (
    <div className="dash">
      <RunProgress run={run} />
      <div className="dash-body">
        <aside className="sidebar">
          <div className="sidebar-header">
            <div className="sidebar-title">
              <strong>Run #{runId}</strong>
              <Link to={`/runs/${runId}/graph`} style={{ fontSize: 12, fontWeight: 500 }}>
                graph →
              </Link>
              {repoId && (
                <button
                  onClick={handleReAnalyzeDocs}
                  disabled={reAnalyzing}
                  title="Run a fresh canonical analysis on the default branch"
                  style={{
                    marginLeft: "auto",
                    padding: "3px 8px",
                    borderRadius: 6,
                    border: "1px solid #d1d5db",
                    background: reAnalyzing ? "#f3f4f6" : "#fff",
                    color: reAnalyzing ? "#9ca3af" : "#374151",
                    cursor: reAnalyzing ? "wait" : "pointer",
                    fontSize: 11,
                  }}
                >
                  {reAnalyzing ? "↻…" : "↻ Re-analyze"}
                </button>
              )}
            </div>
            {run?.repo_full_name && (
              <a
                className="repo-link"
                href={repoUrl(run.repo_full_name)}
                target="_blank"
                rel="noreferrer"
                title={`Open ${run.repo_full_name} on GitHub`}
              >
                <GithubGlyph size={13} />
                <span>{run.repo_full_name}</span>
              </a>
            )}
            {(profile.type || profile.primary_language) && (
              <div className="sidebar-meta">
                {[profile.type, profile.primary_language].filter(Boolean).join(" · ")}
                {sections.length ? ` · ${sections.length} docs` : ""}
              </div>
            )}
          </div>

          <div className="sidebar-search">
            <input
              type="text"
              placeholder="Search docs…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div className="sidebar-tree">
            {docsQ.isLoading ? (
              <SidebarSkeleton />
            ) : filteredTree.length ? (
              <TreeNodes
                nodes={filteredTree}
                depth={0}
                activeId={activeId}
                onPick={setActiveId}
                sectionByPath={sectionByPath}
                forceOpen={!!search.trim()}
              />
            ) : (
              <div style={{ padding: "12px 14px", fontSize: 12, color: "var(--fg-subtle)" }}>
                {search ? "No matching docs." : running ? "Waiting for first sections…" : "No docs yet."}
              </div>
            )}
          </div>
        </aside>

        <main className="doc-main">
          <div className="doc-inner">
            <div className="doc-topbar">
              {activeSection ? (
                <div className="doc-breadcrumbs">
                  {breadcrumbsFor(activeSection.slug_path).map((part, i, arr) => (
                    <span key={i} style={i === arr.length - 1 ? { color: "var(--fg)" } : undefined}>
                      {part}
                      {i < arr.length - 1 && <span className="crumb-sep" style={{ margin: "0 6px" }}>/</span>}
                    </span>
                  ))}
                </div>
              ) : <span />}
              {!chatOpen && (
                <button
                  className="chat-toggle-btn"
                  onClick={() => setChatOpen(true)}
                  title="Open docs chat"
                >
                  <DocsIcon size={16} />
                  <span>Ask docs</span>
                </button>
              )}
            </div>


            {docQ.isLoading && <DocSkeleton />}
            {docQ.error && (
              <div className="doc-empty">
                <div className="doc-empty-icon">!</div>
                <div>Failed to load doc.</div>
              </div>
            )}
            {docQ.data && (
              <RenderedMarkdown
                content={docQ.data.content_md || ""}
                currentSlug={activeSection?.slug_path}
                sectionByPath={sectionByPath}
                onNavigate={setActiveId}
              />
            )}
            {!docQ.data && !docQ.isLoading && !docQ.error && (
              running ? (
                <AgentActivity activity={run?.activity} run={run} />
              ) : (
                <div className="doc-empty">
                  <div className="doc-empty-icon">§</div>
                  <div>Pick a section from the left.</div>
                </div>
              )
            )}
          </div>
        </main>

        {chatOpen && (
          <aside className="chat-sidebar">
            <DocChat
              repoId={repoId}
              activeDocId={activeId}
              activeDocTitle={activeSection?.title}
              onNavigateDoc={(id, anchor) => {
                setActiveId(id);
                if (anchor) {
                  // Defer until the new doc renders.
                  setTimeout(() => {
                    const el = document.getElementById(anchor);
                    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
                  }, 250);
                }
              }}
              onClose={() => setChatOpen(false)}
            />
          </aside>
        )}
      </div>
    </div>
  );
}

function SidebarSkeleton() {
  return (
    <div style={{ padding: "8px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
      {[80, 60, 90, 50, 75, 65].map((w, i) => (
        <div key={i} className="skeleton" style={{ height: 14, width: `${w}%` }} />
      ))}
    </div>
  );
}

function DocSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="skeleton" style={{ height: 32, width: "50%" }} />
      <div className="skeleton" style={{ height: 14, width: "92%", marginTop: 12 }} />
      <div className="skeleton" style={{ height: 14, width: "88%" }} />
      <div className="skeleton" style={{ height: 14, width: "76%" }} />
      <div className="skeleton" style={{ height: 14, width: "84%", marginTop: 18 }} />
      <div className="skeleton" style={{ height: 14, width: "60%" }} />
    </div>
  );
}

function breadcrumbsFor(slugPath) {
  if (!slugPath) return [];
  return slugPath
    .replace(/^\.aura\/docs\//, "")
    .replace(/\.md$/, "")
    .split("/")
    .filter(Boolean);
}

function filterTree(nodes, query, sectionByPath) {
  const out = [];
  for (const n of nodes) {
    if (n.children) {
      const kids = filterTree(n.children, query, sectionByPath);
      if (kids.length || n.label.toLowerCase().includes(query)) {
        out.push({ ...n, children: kids });
      }
    } else {
      if (n.label.toLowerCase().includes(query)) out.push(n);
    }
  }
  return out;
}

function TreeNodes({ nodes, depth, activeId, onPick, sectionByPath, forceOpen }) {
  if (!nodes || !nodes.length) return null;
  return (
    <div>
      {nodes.map((node, idx) => (
        <TreeNode
          key={`${node.label}-${idx}`}
          node={node}
          depth={depth}
          activeId={activeId}
          onPick={onPick}
          sectionByPath={sectionByPath}
          forceOpen={forceOpen}
        />
      ))}
    </div>
  );
}

function TreeNode({ node, depth, activeId, onPick, sectionByPath, forceOpen }) {
  const [open, setOpen] = useState(true);
  const effectiveOpen = forceOpen || open;
  const indent = 8 + depth * 12;
  if (node.children) {
    return (
      <div>
        <button
          className="tree-group-btn"
          onClick={() => setOpen(!effectiveOpen)}
          style={{ paddingLeft: indent }}
        >
          <span className="tree-group-chevron">{effectiveOpen ? "▾" : "▸"}</span>
          <span>{node.label}</span>
        </button>
        {effectiveOpen && (
          <TreeNodes
            nodes={node.children}
            depth={depth + 1}
            activeId={activeId}
            onPick={onPick}
            sectionByPath={sectionByPath}
            forceOpen={forceOpen}
          />
        )}
      </div>
    );
  }
  const section = sectionByPath[node.path];
  const sectionId = node.doc_id || section?.section_id;
  const isActive = activeId === sectionId;
  return (
    <button
      onClick={() => sectionId && onPick(sectionId)}
      className={`tree-leaf-btn ${isActive ? "active" : ""} ${!sectionId ? "disabled" : ""}`}
      style={{ paddingLeft: indent + 8 }}
    >
      <span className="tree-leaf-dot" />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {node.label}
      </span>
    </button>
  );
}

function buildTreeFromSections(sections) {
  // Fallback when no manifest_tree from server: derive from slug_path.
  const root = { _children: {}, _leaves: [] };
  for (const s of sections) {
    const rel = (s.slug_path || "").replace(/^\.aura\/docs\//, "").replace(/\.md$/, "");
    if (!rel) continue;
    const parts = rel.split("/");
    let node = root;
    for (const seg of parts.slice(0, -1)) {
      node._children[seg] ||= { _children: {}, _leaves: [] };
      node = node._children[seg];
    }
    node._leaves.push(s);
  }
  function render(node) {
    const out = [];
    for (const leaf of [...node._leaves].sort((a, b) => a.title.localeCompare(b.title))) {
      out.push({ label: leaf.title, path: leaf.slug_path, doc_id: leaf.section_id });
    }
    for (const name of Object.keys(node._children).sort()) {
      out.push({ label: name, children: render(node._children[name]) });
    }
    return out;
  }
  return render(root);
}

const VERIFIED_RE = /\[verified:\s*([^\]:\s]+):L(\d+)-L(\d+)\]/g;

function rewriteVerified(children) {
  const out = [];
  for (const node of [].concat(children)) {
    if (typeof node !== "string") {
      out.push(node);
      continue;
    }
    let lastIndex = 0;
    let match;
    VERIFIED_RE.lastIndex = 0;
    while ((match = VERIFIED_RE.exec(node)) !== null) {
      if (match.index > lastIndex) {
        out.push(node.slice(lastIndex, match.index));
      }
      out.push(
        <VerifiedBadge
          key={`v-${match.index}`}
          path={match[1]}
          start={match[2]}
          end={match[3]}
        />
      );
      lastIndex = match.index + match[0].length;
    }
    if (lastIndex < node.length) out.push(node.slice(lastIndex));
  }
  return out;
}

function stripFrontMatter(md) {
  if (!md) return "";
  // Strip leading YAML-style front matter (--- ... --- block).
  return md.replace(/^---\n[\s\S]*?\n---\n?/, "");
}

function slugify(text) {
  return String(text)
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function flattenChildrenText(children) {
  let out = "";
  for (const node of [].concat(children)) {
    if (node == null) continue;
    if (typeof node === "string" || typeof node === "number") {
      out += String(node);
    } else if (Array.isArray(node)) {
      out += flattenChildrenText(node);
    } else if (node.props && node.props.children) {
      out += flattenChildrenText(node.props.children);
    }
  }
  return out;
}

function collectHeadingSlugs(md) {
  const slugs = new Set();
  if (!md) return slugs;
  const re = /^(#{1,6})\s+(.+?)\s*$/gm;
  let m;
  while ((m = re.exec(md)) !== null) {
    slugs.add(slugify(m[2]));
  }
  return slugs;
}

function resolveRelativeDocPath(currentSlug, href) {
  if (!href || /^[a-z]+:\/\//i.test(href) || href.startsWith("#") || href.startsWith("mailto:")) {
    return null;
  }
  if (!href.endsWith(".md") && !href.includes(".md#")) return null;
  const [path, hash] = href.split("#");
  const base = (currentSlug || ".aura/docs/index.md").split("/").slice(0, -1);
  const segments = path.split("/");
  const stack = [...base];
  for (const seg of segments) {
    if (seg === "..") stack.pop();
    else if (seg === "" || seg === ".") continue;
    else stack.push(seg);
  }
  const resolved = stack.join("/");
  // Caller may pass paths already prefixed with .aura/docs/ — normalize.
  if (resolved.startsWith(".aura/docs/")) {
    return { path: resolved, hash: hash || null };
  }
  return { path: `.aura/docs/${resolved.replace(/^\.aura\/docs\//, "")}`, hash: hash || null };
}

function RenderedMarkdown({ content, currentSlug, sectionByPath, onNavigate }) {
  const cleaned = useMemo(() => stripFrontMatter(content), [content]);
  const headingSlugs = useMemo(() => collectHeadingSlugs(cleaned), [cleaned]);

  const headingRenderer = (Tag) => ({ children, ...props }) => {
    const slug = slugify(flattenChildrenText(children));
    return (
      <Tag id={slug} {...props}>
        <a
          href={`#${slug}`}
          style={{ color: "inherit", textDecoration: "none" }}
          aria-label="anchor"
        >
          {children}
        </a>
      </Tag>
    );
  };

  return (
    <div className="prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const lang = match ? match[1] : "";
            if (!inline && lang === "mermaid") {
              const src = String(children).replace(/\n$/, "");
              return <Mermaid source={src} />;
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre({ children, ...props }) {
            // If the only child is the rendered Mermaid component, drop the
            // outer <pre> so the SVG isn't trapped in a code block.
            const arr = [].concat(children);
            const first = arr[0];
            if (first && first.type === Mermaid) {
              return <>{children}</>;
            }
            return <pre {...props}>{children}</pre>;
          },
          h1: headingRenderer("h1"),
          h2: headingRenderer("h2"),
          h3: headingRenderer("h3"),
          h4: headingRenderer("h4"),
          h5: headingRenderer("h5"),
          h6: headingRenderer("h6"),
          a({ href, children, ...props }) {
            const resolved =
              sectionByPath && onNavigate
                ? resolveRelativeDocPath(currentSlug, href)
                : null;
            if (resolved && sectionByPath[resolved.path]) {
              const targetId = sectionByPath[resolved.path].section_id;
              return (
                <a
                  href={`#${resolved.path}`}
                  onClick={(e) => {
                    e.preventDefault();
                    onNavigate(targetId);
                    if (resolved.hash) {
                      // Defer hash scroll until the new doc renders.
                      setTimeout(() => {
                        const el = document.getElementById(resolved.hash);
                        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
                      }, 250);
                    }
                  }}
                  style={{
                    color: "var(--accent)",
                    textDecoration: "none",
                    borderBottom: "1px dashed currentColor",
                  }}
                >
                  {children}
                </a>
              );
            }
            // External or unmatched link — open in new tab if absolute.
            const external = href && /^[a-z]+:\/\//i.test(href);
            return (
              <a
                href={href}
                target={external ? "_blank" : undefined}
                rel={external ? "noreferrer" : undefined}
                {...props}
              >
                {children}
              </a>
            );
          },
          p({ children, ...props }) {
            return <p {...props}>{rewriteVerified(children)}</p>;
          },
          li({ children, ...props }) {
            const text = flattenChildrenText(children).trim();
            const slug = slugify(text);
            // Linkify list items whose text matches a heading in the same doc.
            if (text && headingSlugs.has(slug)) {
              return (
                <li {...props}>
                  <a
                    href={`#${slug}`}
                    style={{ color: "var(--accent)", borderBottom: "1px solid transparent" }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderBottomColor = "currentColor")}
                    onMouseLeave={(e) => (e.currentTarget.style.borderBottomColor = "transparent")}
                  >
                    {rewriteVerified(children)}
                  </a>
                </li>
              );
            }
            return <li {...props}>{rewriteVerified(children)}</li>;
          },
        }}
      >
        {cleaned}
      </ReactMarkdown>
    </div>
  );
}
