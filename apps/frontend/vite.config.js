import fs from "node:fs";
import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const DOCS_ROOT = path.resolve(__dirname, "../../docs/docs");
const FRONT_MATTER_RE = /^---\s*\n([\s\S]*?)\n---\s*\n?/;

function walkMarkdownFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkMarkdownFiles(fullPath));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(fullPath);
    }
  }

  return files;
}

function parseFrontMatter(markdown) {
  const match = markdown.match(FRONT_MATTER_RE);
  if (!match) {
    return {};
  }

  return match[1]
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .reduce((acc, line) => {
      const separator = line.indexOf(":");
      if (separator === -1) {
        return acc;
      }

      const key = line.slice(0, separator).trim();
      const rawValue = line.slice(separator + 1).trim();

      try {
        acc[key] = JSON.parse(rawValue);
      } catch {
        acc[key] = rawValue.replace(/^"(.*)"$/, "$1");
      }

      return acc;
    }, {});
}

function diataxisForCategory(category) {
  if (["project", "architecture", "flow"].includes(category)) {
    return "explanation";
  }

  if (category === "config") {
    return "how-to";
  }

  return "reference";
}

function loadDocsFixture() {
  const files = walkMarkdownFiles(DOCS_ROOT).sort((left, right) => left.localeCompare(right));
  const rawDocs = files.map((filePath) => {
    const markdown = fs.readFileSync(filePath, "utf8");
    const frontMatter = parseFrontMatter(markdown);
    const relativePath = path.relative(DOCS_ROOT, filePath).replaceAll(path.sep, "/");

    return {
      artifact_id: frontMatter.artifact_id || relativePath,
      category: frontMatter.category || "reference",
      title: frontMatter.name || relativePath,
      relative_path: relativePath,
      slug_path: `.aura/docs/${relativePath}`,
      content_md: markdown,
      source_files: Array.isArray(frontMatter.source_files) ? frontMatter.source_files : [],
      source_lines: frontMatter.source_lines && typeof frontMatter.source_lines === "object" ? frontMatter.source_lines : {},
    };
  });

  const idCounts = rawDocs.reduce((acc, doc) => {
    acc.set(doc.artifact_id, (acc.get(doc.artifact_id) || 0) + 1);
    return acc;
  }, new Map());

  const docs = rawDocs.map((doc) => ({
    ...doc,
    artifact_id: idCounts.get(doc.artifact_id) > 1 ? doc.relative_path : doc.artifact_id,
  }));

  return {
    docs,
    docsById: new Map(docs.map((doc) => [doc.artifact_id, doc])),
  };
}

function sendJson(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(payload));
}

function localDocsMockPlugin() {
  let fixture = loadDocsFixture();

  return {
    configureServer(server) {
      server.watcher.add(DOCS_ROOT);
      server.watcher.on("add", () => {
        fixture = loadDocsFixture();
      });
      server.watcher.on("change", () => {
        fixture = loadDocsFixture();
      });
      server.watcher.on("unlink", () => {
        fixture = loadDocsFixture();
      });

      server.middlewares.use((req, res, next) => {
        const url = req.url || "";
        const method = req.method || "GET";

        if (method === "GET" && url === "/api/v1/auth/github/me") {
          sendJson(res, 200, { id: "local-demo-user", login: "local-demo" });
          return;
        }

        if (method === "GET" && url === "/api/v1/github/repos/oauth") {
          sendJson(res, 200, {
            repos: [
              {
                id: "local-docs-source",
                full_name: "local/demo-docs",
                owner: "local",
                name: "demo-docs",
                default_branch: "main",
                private: false,
              },
            ],
          });
          return;
        }

        if (method === "POST" && url === "/api/v1/repos/analyze") {
          sendJson(res, 200, {
            run_id: 1,
            repo_id: 1,
            status: "queued",
          });
          return;
        }

        const indexMatch = url.match(/^\/api\/v1\/repos\/[^/]+\/docs\/index$/);
        if (method === "GET" && indexMatch) {
          sendJson(res, 200, {
            repo_id: 1,
            run_id: 1,
            sections: fixture.docs.map((doc) => ({
              section_id: doc.artifact_id,
              title: doc.title,
              diataxis_type: diataxisForCategory(doc.category),
              slug_path: doc.slug_path,
            })),
          });
          return;
        }

        const sectionMatch = url.match(/^\/api\/v1\/repos\/[^/]+\/docs\/([^/?#]+)$/);
        if (method === "GET" && sectionMatch) {
          const sectionId = decodeURIComponent(sectionMatch[1]);
          const doc = fixture.docsById.get(sectionId);

          if (!doc) {
            sendJson(res, 404, { detail: "section_not_found" });
            return;
          }

          sendJson(res, 200, {
            section_id: doc.artifact_id,
            title: doc.title,
            diataxis_type: diataxisForCategory(doc.category),
            content_md: doc.content_md,
            provenance: doc.source_files.map((sourceFile) => {
              const lineRange = doc.source_lines[sourceFile] || [null, null];

              return {
                source_file: sourceFile,
                source_line_start: lineRange[0],
                source_line_end: lineRange[1],
                confidence: 1.0,
              };
            }),
          });
          return;
        }

        next();
      });
    },
    name: "local-docs-mock",
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const useLocalDocsMock = env.AURA_USE_LOCAL_DOCS_MOCK === "1";

  return {
    plugins: [react(), ...(useLocalDocsMock ? [localDocsMockPlugin()] : [])],
  };
});
