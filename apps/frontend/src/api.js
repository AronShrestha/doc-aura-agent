export const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001/api/v1";

export async function readErrorDetail(res, fallback) {
  try {
    const payload = await res.json();
    if (payload?.detail) {
      return String(payload.detail);
    }
  } catch {}

  return fallback;
}
