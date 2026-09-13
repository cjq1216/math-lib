/**
 * API 客户端：内存 access token、HttpOnly refresh cookie、统一 401 恢复。
 */
import type { AuthResponse } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "";
const AUTH_ENDPOINTS = new Set([
  "/api/v1/auth/login",
  "/api/v1/auth/register",
  "/api/v1/auth/refresh",
]);

let accessToken: string | null = null;
let refreshPromise: Promise<string | null> | null = null;

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function clearAccessToken() {
  accessToken = null;
}

function redirectToLogin() {
  if (typeof window === "undefined" || window.location.pathname === "/login") return;
  const next = `${window.location.pathname}${window.location.search}`;
  window.location.href = `/login?next=${encodeURIComponent(next)}`;
}

async function parseError(response: Response): Promise<string> {
  const data = await response.json().catch(() => null);
  if (typeof data?.detail === "string") return data.detail;
  if (data?.detail) return JSON.stringify(data.detail);
  return response.statusText || "请求失败";
}

export async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const response = await fetch(`${BASE}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        clearAccessToken();
        return null;
      }
      const data = (await response.json()) as AuthResponse;
      setAccessToken(data.access_token);
      return data.access_token;
    } catch {
      clearAccessToken();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

async function request(
  path: string,
  options: RequestInit = {},
  allowRetry = true,
): Promise<Response> {
  const headers = new Headers(options.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${BASE}${path}`, {
    ...options,
    credentials: "include",
    headers,
  });
  if (response.status !== 401) return response;

  if (allowRetry && !AUTH_ENDPOINTS.has(path)) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return request(path, options, false);
  }

  clearAccessToken();
  if (!AUTH_ENDPOINTS.has(path)) redirectToLogin();
  return response;
}

async function json<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await request(path, options);
  if (!response.ok) throw new ApiError(response.status, await parseError(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  return json<T>(path, options);
}

export const http = {
  get: <T>(path: string) => json<T>(path, { method: "GET" }),

  post: <T>(path: string, body?: unknown) =>
    json<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),

  patch: <T>(path: string, body?: unknown) =>
    json<T>(path, {
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),

  put: <T>(path: string, body?: unknown) =>
    json<T>(path, {
      method: "PUT",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),

  del: <T>(path: string) => json<T>(path, { method: "DELETE" }),

  upload: async <T>(path: string, file: File): Promise<T> => {
    const form = new FormData();
    form.append("file", file);
    return json<T>(path, { method: "POST", body: form });
  },

  download: async (path: string, filename: string): Promise<void> => {
    const response = await request(path, { method: "GET" });
    if (!response.ok) throw new ApiError(response.status, await parseError(response));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
};

export function qs(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      search.append(key, String(value));
    }
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}
