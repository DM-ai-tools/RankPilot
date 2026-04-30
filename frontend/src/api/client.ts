/**
 * Central HTTP client — components use TanStack Query hooks that call these helpers.
 * Do not call fetch() directly from UI components.
 */

import { useAuthStore } from "../stores/authStore";

const defaultBase = "";

/** VITE_API_BASE_URL at build time; strip trailing `/` so paths like `/api/v1/...` do not become `//api/...`. */
function viteApiBase(): string {
  return String(import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
}

function authHeaders(): HeadersInit {
  const token = useAuthStore.getState().accessToken;
  return {
    Accept: "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/**
 * Stale or invalid RankPilot JWT — clear and send user to login (skip on /login).
 * Do NOT treat 401 from Google sub-integrations as session loss (e.g. expired GBP refresh).
 */
function signOutIfUnauthorized(status: number, apiPath: string): void {
  if (status !== 401) return;
  const p = (apiPath.split("?")[0] ?? "").toLowerCase();
  if (p.includes("/api/v1/integrations/")) return;
  useAuthStore.getState().setAccessToken(null);
  useAuthStore.getState().setNeedsOnboarding(true);
  if (typeof window === "undefined" || window.location.pathname.startsWith("/login")) return;
  window.location.assign("/login");
}

/** Readable message from API error (unwraps FastAPI `{"detail":"..."}`). */
export function formatApiError(err: unknown): string {
  if (!(err instanceof Error)) return "Request failed";
  const raw = err.message.trim();
  if (!raw.startsWith("{")) return raw;
  try {
    const j = JSON.parse(raw) as { detail?: string | { msg?: string }[] };
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) {
      return j.detail
        .map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: string }).msg) : JSON.stringify(x)))
        .join("; ");
    }
  } catch {
    /* ignore */
  }
  return raw;
}

export async function apiGet<T>(path: string): Promise<T> {
  const base = viteApiBase() || defaultBase;
  const res = await fetch(`${base}${path}`, { headers: authHeaders() });
  if (!res.ok) {
    signOutIfUnauthorized(res.status, path);
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export async function apiPostJson<T, B = unknown>(path: string, body: B): Promise<T> {
  const base = viteApiBase() || defaultBase;
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    signOutIfUnauthorized(res.status, path);
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export async function apiPatchJson<T, B = unknown>(path: string, body: B): Promise<T> {
  const base = viteApiBase() || defaultBase;
  const res = await fetch(`${base}${path}`, {
    method: "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    signOutIfUnauthorized(res.status, path);
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export async function apiDelete<T = unknown>(path: string): Promise<T> {
  const base = viteApiBase() || defaultBase;
  const res = await fetch(`${base}${path}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    signOutIfUnauthorized(res.status, path);
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

/** POST without Bearer (e.g. login). */
export async function apiPostPublic<T, B = unknown>(path: string, body: B): Promise<T> {
  const base = viteApiBase() || defaultBase;
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}
