import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link, useNavigate, useParams } from "react-router-dom";
import { API, readErrorDetail } from "../api";

const DOCS_PREFIX = ".aura/docs/";

function toRelativeDocPath(slugPath) {
  if (!slugPath) {
    return "";
  }

  return slugPath.startsWith(DOCS_PREFIX) ? slugPath.slice(DOCS_PREFIX.length) : slugPath;
}

function docRoute(repoId, sectionId, hash = "") {
  return `/repos/${repoId}/docs/${encodeURIComponent(sectionId)}${hash}`;
}

function buildBasenameLookup(sections) {
  const counts = new Map();

  for (const section of sections) {
    const basename = toRelativeDocPath(section.slug_path).split("/").pop()?.toLowerCase();
    if (!basename) {
      continue;
    }
    counts.set(basename, (counts.get(basename) || 0) + 1);
  }

  const lookup = new Map();

  for (const section of sections) {
    const basename = toRelativeDocPath(section.slug_path).split("/").pop()?.toLowerCase();
    if (!basename || counts.get(basename) !== 1) {
      continue;
    }
    lookup.set(basename, section.section_id);
  }

  return lookup;
}

function resolveDocLink(href, currentSlugPath, slugToSectionMap, basenameToSectionMap, fallbackSectionId) {
  if (!href || href.startsWith("#") || /^[a-z][a-z\d+.-]*:/i.test(href)) {
    return null;
  }

  const [rawPath, rawHash] = href.split("#", 2);
  if (!rawPath.toLowerCase().endsWith(".md")) {
    return null;
  }

  try {
    const currentRelativePath = toRelativeDocPath(currentSlugPath);
    const baseDir = currentRelativePath.includes("/")
      ? currentRelativePath.slice(0, currentRelativePath.lastIndexOf("/") + 1)
      : "";
    const baseUrl = `https://aura.local/${baseDir}`;
    const resolvedPath = decodeURIComponent(new URL(rawPath, baseUrl).pathname.replace(/^\//, ""));
    const resolvedCandidates = [
      toRelativeDocPath(resolvedPath),
      toRelativeDocPath(rawPath.replace(/^\.\//, "").replace(/^\//, "")),
    ].filter(Boolean);

    for (const candidate of resolvedCandidates) {
      const sectionId = slugToSectionMap.get(candidate);
      if (sectionId) {
        return {
          hash: rawHash ? `#${rawHash}` : "",
          sectionId,
        };
      }
    }

    const basename = resolvedCandidates
      .map((candidate) => candidate.split("/").pop()?.toLowerCase())
      .find(Boolean);

    if (basename) {
      const uniqueSectionId = basenameToSectionMap.get(basename);
      if (uniqueSectionId) {
        return {
          hash: rawHash ? `#${rawHash}` : "",
          sectionId: uniqueSectionId,
        };
      }

      if (basename === "readme.md" && fallbackSectionId) {
        return {
          hash: rawHash ? `#${rawHash}` : "",
          sectionId: fallbackSectionId,
        };
      }
    }

    return null;
  } catch {
    return null;
  }
}

function formatLineRange(item) {
  if (item.source_line_start == null) {
    return "";
  }

  if (item.source_line_end == null || item.source_line_end === item.source_line_start) {
    return `:${item.source_line_start}`;
  }

  return `:${item.source_line_start}-${item.source_line_end}`;
}

function stripFrontMatter(markdown) {
  if (!markdown) {
    return "";
  }

  return markdown.replace(/^---\s*\n[\s\S]*?\n---\s*\n?/, "");
}

function formatStructureLabel(value) {
  return value
    .replace(/\.md$/i, "")
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => {
      if (part.length <= 3) {
        return part.toUpperCase();
      }

      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join(" ");
}

function createFolderNode(segment, fullPath) {
  return {
    children: [],
    docCount: 0,
    fullPath,
    key: `folder:${fullPath}`,
    label: formatStructureLabel(segment),
    segment,
    type: "folder",
  };
}

function createDocNode(section, relativePath) {
  const fileName = relativePath.split("/").pop() || relativePath;

  return {
    fileName,
    key: `doc:${section.section_id}`,
    label: section.title,
    relativePath,
    section,
    type: "doc",
  };
}

function sortNavigationNodes(nodes) {
  const sorted = nodes.map((node) => {
    if (node.type !== "folder") {
      return node;
    }

    const children = sortNavigationNodes(node.children);
    return {
      ...node,
      children,
      docCount: children.reduce((count, child) => count + (child.type === "doc" ? 1 : child.docCount), 0),
    };
  });

  return sorted.sort((left, right) => {
    if (left.type !== right.type) {
      return left.type === "folder" ? -1 : 1;
    }

    if (left.type === "folder") {
      return left.label.localeCompare(right.label);
    }

    const leftPriority = left.fileName === "overview.md" ? -2 : left.fileName === "index.md" ? -1 : 0;
    const rightPriority = right.fileName === "overview.md" ? -2 : right.fileName === "index.md" ? -1 : 0;

    if (leftPriority !== rightPriority) {
      return leftPriority - rightPriority;
    }

    return left.label.localeCompare(right.label);
  });
}

function buildNavigationGraph(sections) {
  const entrySection = sections.find((section) => toRelativeDocPath(section.slug_path) === "index.md") || null;
  const rootNodes = [];

  for (const section of sections) {
    if (entrySection && section.section_id === entrySection.section_id) {
      continue;
    }

    const relativePath = toRelativeDocPath(section.slug_path);
    const segments = relativePath.split("/");
    let currentLevel = rootNodes;
    const parents = [];

    for (let index = 0; index < segments.length; index += 1) {
      const segment = segments[index];
      const isFile = index === segments.length - 1;

      if (isFile) {
        currentLevel.push(createDocNode(section, relativePath));
        break;
      }

      parents.push(segment);
      const fullPath = parents.join("/");
      let folder = currentLevel.find((node) => node.type === "folder" && node.segment === segment);

      if (!folder) {
        folder = createFolderNode(segment, fullPath);
        currentLevel.push(folder);
      }

      currentLevel = folder.children;
    }
  }

  return {
    entrySection,
    nodes: sortNavigationNodes(rootNodes),
    totalSections: sections.length,
  };
}

function flattenDocNodes(nodes, acc = []) {
  for (const node of nodes) {
    if (node.type === "doc") {
      acc.push(node);
      continue;
    }

    flattenDocNodes(node.children, acc);
  }

  return acc;
}

function findBranchForSection(nodes, sectionId, trail = []) {
  for (const node of nodes) {
    if (node.type === "doc") {
      if (node.section.section_id === sectionId) {
        return {
          docNode: node,
          trail,
        };
      }

      continue;
    }

    const match = findBranchForSection(node.children, sectionId, [...trail, node]);
    if (match) {
      return match;
    }
  }

  return null;
}

const GRAPH_METRICS = {
  columnGap: 284,
  paddingX: 28,
  paddingY: 28,
  rowGap: 116,
  sizes: {
    doc: { height: 84, width: 244 },
    folder: { height: 72, width: 196 },
    root: { height: 92, width: 244 },
  },
};

function makeGraphEdgePath(fromNode, toNode) {
  const startX = fromNode.x + fromNode.width;
  const startY = fromNode.y + fromNode.height / 2;
  const endX = toNode.x;
  const endY = toNode.y + toNode.height / 2;
  const bend = Math.max(48, (endX - startX) * 0.45);

  return `M ${startX} ${startY} C ${startX + bend} ${startY}, ${endX - bend} ${endY}, ${endX} ${endY}`;
}

function buildGraphCanvas(navigationGraph, activeSectionId, repoId) {
  const nodes = [];
  const edges = [];
  let cursor = 0;
  let maxDepth = 0;

  function visit(item, depth, parentId) {
    maxDepth = Math.max(maxDepth, depth);

    if (item.type === "doc") {
      const size = GRAPH_METRICS.sizes.doc;
      const order = cursor;
      cursor += 1;
      const selected = item.section.section_id === activeSectionId;
      const active = selected;

      nodes.push({
        active,
        depth,
        height: size.height,
        id: item.key,
        kind: "doc",
        label: item.label,
        meta: item.relativePath,
        route: docRoute(repoId, item.section.section_id),
        selected,
        width: size.width,
        x: GRAPH_METRICS.paddingX + depth * GRAPH_METRICS.columnGap,
        y: GRAPH_METRICS.paddingY + order * GRAPH_METRICS.rowGap,
      });

      if (parentId) {
        edges.push({ active, from: parentId, to: item.key });
      }

      return {
        active,
        max: order,
        min: order,
        mid: order,
      };
    }

    const children = item.children || [];
    const childLayouts = children.map((child) => visit(child, depth + 1, item.key));
    const size = GRAPH_METRICS.sizes[item.type];
    const selected = item.type === "root" && item.section?.section_id === activeSectionId;
    const active = selected || childLayouts.some((child) => child.active);
    const min = childLayouts.length ? Math.min(...childLayouts.map((child) => child.min)) : cursor;
    const max = childLayouts.length ? Math.max(...childLayouts.map((child) => child.max)) : cursor;
    const mid = childLayouts.length ? (min + max) / 2 : cursor;

    if (!childLayouts.length) {
      cursor += 1;
    }

    nodes.push({
      active,
      count: item.docCount || childLayouts.length,
      depth,
      height: size.height,
      id: item.key,
      kind: item.type,
      label: item.label,
      meta: item.type === "root" ? item.relativePath || "docs index" : `${item.fullPath}/`,
      route: item.type === "root" && item.section ? docRoute(repoId, item.section.section_id) : "",
      selected,
      width: size.width,
      x: GRAPH_METRICS.paddingX + depth * GRAPH_METRICS.columnGap,
      y: GRAPH_METRICS.paddingY + mid * GRAPH_METRICS.rowGap,
    });

    if (parentId) {
      edges.push({ active, from: parentId, to: item.key });
    }

    return { active, max, min, mid };
  }

  const rootItem = navigationGraph.entrySection
    ? {
        children: navigationGraph.nodes,
        key: `root:${navigationGraph.entrySection.section_id}`,
        label: navigationGraph.entrySection.title,
        relativePath: toRelativeDocPath(navigationGraph.entrySection.slug_path),
        section: navigationGraph.entrySection,
        type: "root",
      }
    : {
        children: navigationGraph.nodes,
        key: "root:docs",
        label: "Documentation",
        relativePath: "",
        section: null,
        type: "root",
      };

  visit(rootItem, 0, "");

  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const laidOutEdges = edges
    .map((edge) => {
      const fromNode = nodeById.get(edge.from);
      const toNode = nodeById.get(edge.to);

      if (!fromNode || !toNode) {
        return null;
      }

      return {
        ...edge,
        path: makeGraphEdgePath(fromNode, toNode),
      };
    })
    .filter(Boolean);

  const width = nodes.length
    ? Math.max(...nodes.map((node) => node.x + node.width)) + GRAPH_METRICS.paddingX
    : GRAPH_METRICS.paddingX * 2;
  const height = nodes.length
    ? Math.max(...nodes.map((node) => node.y + node.height)) + GRAPH_METRICS.paddingY
    : GRAPH_METRICS.paddingY * 2;

  return {
    depthCount: maxDepth + 1,
    edges: laidOutEdges,
    folderCount: nodes.filter((node) => node.kind === "folder").length,
    height,
    nodes,
    width,
  };
}

function GraphCanvas({ graphCanvas }) {
  return (
    <div className="docs-graph-scroll">
      <div
        className="docs-graph-stage"
        style={{ height: `${graphCanvas.height}px`, width: `${graphCanvas.width}px` }}
      >
        <svg
          aria-hidden="true"
          className="docs-graph-edges"
          preserveAspectRatio="none"
          viewBox={`0 0 ${graphCanvas.width} ${graphCanvas.height}`}
        >
          {graphCanvas.edges.map((edge) => (
            <path
              className={`docs-graph-edge${edge.active ? " active" : ""}`}
              d={edge.path}
              key={`${edge.from}-${edge.to}`}
            />
          ))}
        </svg>

        {graphCanvas.nodes.map((node) => {
          const className = `docs-graph-node docs-graph-node--${node.kind}${node.active ? " active" : ""}`;
          const style = {
            left: `${node.x}px`,
            minHeight: `${node.height}px`,
            top: `${node.y}px`,
            width: `${node.width}px`,
          };

          const body = (
            <>
              <span className="docs-graph-node-kicker">
                {node.kind === "root" ? "Entry" : node.kind === "folder" ? "Cluster" : "Document"}
              </span>
              <strong className="docs-graph-node-title">{node.label}</strong>
              <span className="docs-graph-node-meta">{node.meta}</span>
              {node.kind === "folder" ? <span className="docs-graph-node-badge">{node.count}</span> : null}
            </>
          );

          if (node.route) {
            return (
              <Link
                aria-current={node.selected ? "page" : undefined}
                className={className}
                key={node.id}
                style={style}
                to={node.route}
              >
                {body}
              </Link>
            );
          }

          return (
            <div className={className} key={node.id} style={style}>
              {body}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function DocsScreen({ connectAuth, loadingSession, onSessionExpired, session }) {
  const navigate = useNavigate();
  const { repoId, sectionId = "" } = useParams();

  const [sections, setSections] = useState([]);
  const [doc, setDoc] = useState(null);
  const [loadingIndex, setLoadingIndex] = useState(true);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [indexError, setIndexError] = useState("");
  const [docError, setDocError] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);

  const selectedSection = sections.find((section) => section.section_id === sectionId) || null;
  const slugToSectionMap = useMemo(
    () => new Map(sections.map((section) => [toRelativeDocPath(section.slug_path), section.section_id])),
    [sections],
  );
  const basenameToSectionMap = useMemo(() => buildBasenameLookup(sections), [sections]);
  const navigationGraph = useMemo(() => buildNavigationGraph(sections), [sections]);
  const graphCanvas = useMemo(
    () => buildGraphCanvas(navigationGraph, selectedSection?.section_id || "", repoId),
    [navigationGraph, repoId, selectedSection],
  );
  const fallbackSectionId = useMemo(() => {
    const projectOverview = slugToSectionMap.get("project-overview.md");
    if (projectOverview) {
      return projectOverview;
    }

    return slugToSectionMap.get("index.md") || "";
  }, [slugToSectionMap]);
  const branchMatch = useMemo(
    () => findBranchForSection(navigationGraph.nodes, selectedSection?.section_id || ""),
    [navigationGraph.nodes, selectedSection],
  );
  const flattenedDocs = useMemo(() => flattenDocNodes(navigationGraph.nodes), [navigationGraph.nodes]);
  const selectedDocIndex = selectedSection
    ? flattenedDocs.findIndex((item) => item.section.section_id === selectedSection.section_id)
    : -1;
  const previousDoc = selectedDocIndex > 0 ? flattenedDocs[selectedDocIndex - 1] : null;
  const nextDoc =
    selectedDocIndex >= 0 && selectedDocIndex < flattenedDocs.length - 1 ? flattenedDocs[selectedDocIndex + 1] : null;
  const renderedMarkdown = doc ? stripFrontMatter(doc.content_md) : "";
  const selectedRelativePath = selectedSection ? toRelativeDocPath(selectedSection.slug_path) : "";
  const selectedTrail = branchMatch ? [...branchMatch.trail.map((node) => node.label), branchMatch.docNode.label] : [];

  useEffect(() => {
    if (loadingSession || !session) {
      return;
    }

    let cancelled = false;

    async function loadIndex() {
      setLoadingIndex(true);
      setIndexError("");
      setDocError("");
      setDoc(null);

      try {
        const res = await fetch(`${API}/repos/${repoId}/docs/index`, {
          credentials: "include",
          cache: "no-store",
        });

        if (cancelled) {
          return;
        }

        if (res.status === 401) {
          onSessionExpired("Session expired. Sign in again.");
          return;
        }

        if (res.status === 404) {
          setSections([]);
          return;
        }

        if (!res.ok) {
          setIndexError(await readErrorDetail(res, "Failed to load documentation index."));
          setSections([]);
          return;
        }

        const data = await res.json();
        setSections(data.sections || []);
      } catch {
        if (!cancelled) {
          setIndexError("Network error while loading documentation index.");
          setSections([]);
        }
      } finally {
        if (!cancelled) {
          setLoadingIndex(false);
        }
      }
    }

    loadIndex();

    return () => {
      cancelled = true;
    };
  }, [loadingSession, onSessionExpired, refreshTick, repoId, session]);

  useEffect(() => {
    if (!sectionId && sections.length > 0) {
      navigate(docRoute(repoId, sections[0].section_id), { replace: true });
    }
  }, [navigate, repoId, sectionId, sections]);

  useEffect(() => {
    if (loadingSession || !session || !sectionId || sections.length === 0) {
      return;
    }

    if (!selectedSection) {
      setDoc(null);
      setDocError("Requested section was not found in the generated docs index.");
      return;
    }

    let cancelled = false;

    async function loadDoc() {
      setLoadingDoc(true);
      setDocError("");

      try {
        const res = await fetch(`${API}/repos/${repoId}/docs/${encodeURIComponent(sectionId)}`, {
          credentials: "include",
          cache: "no-store",
        });

        if (cancelled) {
          return;
        }

        if (res.status === 401) {
          onSessionExpired("Session expired. Sign in again.");
          return;
        }

        if (!res.ok) {
          setDoc(null);
          setDocError(await readErrorDetail(res, "Failed to load documentation section."));
          return;
        }

        setDoc(await res.json());
      } catch {
        if (!cancelled) {
          setDoc(null);
          setDocError("Network error while loading documentation section.");
        }
      } finally {
        if (!cancelled) {
          setLoadingDoc(false);
        }
      }
    }

    loadDoc();

    return () => {
      cancelled = true;
    };
  }, [loadingSession, onSessionExpired, repoId, sectionId, sections.length, selectedSection, session]);

  if (loadingSession) {
    return (
      <div className="page page--docs">
        <div className="card">
          <p>Checking session...</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="page page--docs">
        <header className="page-header">
          <div>
            <h1>Aura Docs</h1>
            <p className="muted">Sign in to load the generated documentation.</p>
          </div>
          <Link className="button-link secondary-button" to="/">
            Back to Setup
          </Link>
        </header>

        <div className="card">
          <p>Your session is not active.</p>
          <div className="row">
            <button type="button" onClick={connectAuth}>
              Sign in with GitHub
            </button>
          </div>
        </div>
      </div>
    );
  }

  const showEmptyState = !loadingIndex && !indexError && sections.length === 0;

  return (
    <div className="page page--docs">
      <header className="page-header">
        <div>
          <h1>Aura Docs</h1>
          <p className="muted">Generated documentation for analyzed repository #{repoId}.</p>
        </div>
        <div className="row row--compact">
          <button type="button" onClick={() => setRefreshTick((tick) => tick + 1)}>
            Refresh Docs
          </button>
          <Link className="button-link secondary-button" to="/">
            Back to Setup
          </Link>
        </div>
      </header>

      {indexError ? <div className="card error-card">{indexError}</div> : null}

      {showEmptyState ? (
        <div className="card empty-state">
          <h3>No generated docs yet</h3>
          <p>Run analysis from the setup screen, then refresh this view after the latest run completes.</p>
        </div>
      ) : (
        <>
          <section className="card docs-graph-panel">
            <div className="docs-graph-panel-header">
              <div>
                <p className="eyebrow">Navigation Graph</p>
                <h2>Node map for the generated docs</h2>
                <p className="muted compact">
                  Click any document node to move through the docs. Highlighted edges show the active branch.
                </p>
              </div>

              <div className="docs-graph-stats" aria-label="Graph summary">
                <div className="docs-graph-stat">
                  <span className="docs-graph-stat-label">Docs</span>
                  <strong>{navigationGraph.totalSections}</strong>
                </div>
                <div className="docs-graph-stat">
                  <span className="docs-graph-stat-label">Clusters</span>
                  <strong>{graphCanvas.folderCount}</strong>
                </div>
                <div className="docs-graph-stat">
                  <span className="docs-graph-stat-label">Levels</span>
                  <strong>{graphCanvas.depthCount}</strong>
                </div>
              </div>
            </div>

            <GraphCanvas graphCanvas={graphCanvas} />
          </section>

          <div className="docs-shell docs-shell--single">
            <section className="docs-content docs-content--wide">
            {loadingDoc ? <p className="muted">Loading section...</p> : null}
            {docError ? <div className="error-card">{docError}</div> : null}

            {doc ? (
              <>
                <div className="docs-context-bar">
                  <div aria-label="Current document path" className="doc-breadcrumbs">
                    {selectedTrail.map((part, index) => (
                      <span className="doc-breadcrumb" key={`${part}-${index}`}>
                        {part}
                      </span>
                    ))}
                  </div>

                  <div className="docs-context-tags">
                    {branchMatch?.trail.at(-1) ? (
                      <span className="docs-context-tag">{branchMatch.trail.at(-1).label}</span>
                    ) : null}
                    <span className="docs-context-tag subtle">{doc.diataxis_type}</span>
                  </div>
                </div>

                <article className="docs-article">
                  <div className="docs-article-header">
                    <p className="eyebrow">Current Section</p>
                    <h2>{doc.title}</h2>
                    <p className="doc-path">{selectedRelativePath}</p>
                  </div>

                  <div className="doc-rail">
                    {previousDoc ? (
                      <Link className="doc-rail-link" to={docRoute(repoId, previousDoc.section.section_id)}>
                        <span className="doc-rail-direction">Previous</span>
                        <strong>{previousDoc.label}</strong>
                      </Link>
                    ) : <span />}

                    {nextDoc ? (
                      <Link className="doc-rail-link" to={docRoute(repoId, nextDoc.section.section_id)}>
                        <span className="doc-rail-direction">Next</span>
                        <strong>{nextDoc.label}</strong>
                      </Link>
                    ) : <span />}
                  </div>

                  <div className="markdown-body">
                    <ReactMarkdown
                      components={{
                        a({ children, href, ...props }) {
                          const resolved = resolveDocLink(
                            href,
                            selectedSection?.slug_path,
                            slugToSectionMap,
                            basenameToSectionMap,
                            fallbackSectionId,
                          );

                          if (resolved) {
                            return <Link to={docRoute(repoId, resolved.sectionId, resolved.hash)}>{children}</Link>;
                          }

                          const external = Boolean(href && /^[a-z][a-z\d+.-]*:/i.test(href));

                          return (
                            <a
                              {...props}
                              href={href}
                              rel={external ? "noreferrer" : undefined}
                              target={external ? "_blank" : undefined}
                            >
                              {children}
                            </a>
                          );
                        },
                      }}
                      remarkPlugins={[remarkGfm]}
                    >
                      {renderedMarkdown}
                    </ReactMarkdown>
                  </div>

                  {doc.provenance?.length ? (
                    <div className="provenance">
                      <h3>Source Provenance</h3>
                      <ul className="provenance-list">
                        {doc.provenance.map((item) => (
                          <li
                            key={`${item.source_file}:${item.source_line_start ?? "none"}:${item.source_line_end ?? "none"}`}
                          >
                            <code>
                              {item.source_file}
                              {formatLineRange(item)}
                            </code>
                            <span className="provenance-confidence">
                              Confidence {item.confidence.toFixed(1)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </article>
              </>
            ) : null}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
