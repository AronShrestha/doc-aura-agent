import axios from "axios";
import { useQuery } from "@tanstack/react-query";

export const API = "http://localhost:8001/api/v1";
export const TOKEN_KEY = "aura_token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export const client = axios.create({ baseURL: API });

client.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401) {
      setToken("");
      if (onUnauthorized) onUnauthorized();
    }
    return Promise.reject(err);
  },
);

// ---------------------------------------------------------------------------
// React-Query hooks
// ---------------------------------------------------------------------------

export function useMe(options = {}) {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => (await client.get(`/auth/me`)).data,
    retry: false,
    ...options,
  });
}

export function useMyRepos(options = {}) {
  return useQuery({
    queryKey: ["my-repos"],
    queryFn: async () => (await client.get(`/me/repos`)).data,
    refetchInterval: (q) => {
      const repos = q.state.data?.repos || [];
      const running = repos.some(
        (r) => r.latest_run && !["succeeded", "failed"].includes(r.latest_run.status),
      );
      return running ? 3000 : false;
    },
    ...options,
  });
}

export function useRun(runId, options = {}) {
  return useQuery({
    queryKey: ["run", runId],
    enabled: !!runId,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status && status !== "succeeded" && status !== "failed" ? 3000 : false;
    },
    queryFn: async () => (await client.get(`/runs/${runId}`)).data,
    ...options,
  });
}

export function useDocs(repoId) {
  return useQuery({
    queryKey: ["docs", repoId],
    enabled: !!repoId,
    queryFn: async () => (await client.get(`/repos/${repoId}/docs/index`)).data,
  });
}

export function useDoc(repoId, sectionId) {
  return useQuery({
    queryKey: ["doc", repoId, sectionId],
    enabled: !!repoId && !!sectionId,
    queryFn: async () =>
      (await client.get(`/repos/${repoId}/docs/${sectionId}`)).data,
  });
}

export function useGraph(repoId, prRunId) {
  return useQuery({
    queryKey: ["graph", repoId, prRunId || null],
    enabled: !!repoId,
    queryFn: async () => {
      const params = prRunId ? { pr_run_id: prRunId } : {};
      return (await client.get(`/repos/${repoId}/graph`, { params })).data;
    },
  });
}

export function usePrImpact(pullRequestId) {
  return useQuery({
    queryKey: ["pr-impact", pullRequestId],
    enabled: !!pullRequestId,
    queryFn: async () =>
      (await client.get(`/pull-requests/${pullRequestId}/impact`)).data,
  });
}

export function usePrDocDiff(pullRequestId) {
  return useQuery({
    queryKey: ["pr-doc-diff", pullRequestId],
    enabled: !!pullRequestId,
    queryFn: async () =>
      (await client.get(`/pull-requests/${pullRequestId}/doc-diff`)).data,
  });
}

export function useGeneratedDoc(repoId, artifactId) {
  return useQuery({
    queryKey: ["gen-doc", repoId, artifactId],
    enabled: !!repoId && !!artifactId,
    queryFn: async () =>
      (await client.get(`/repos/${repoId}/generated-docs/${artifactId}`)).data,
  });
}
