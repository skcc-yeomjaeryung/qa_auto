/** Control Plane fetch with X-User-Id (M1 auth gate). */

import { getCurrentUserId } from "./user";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

export function apiUrl(path: string): string {
  if (path.startsWith("http")) return path;
  return `${API}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  if (!headers.has("X-User-Id")) {
    headers.set("X-User-Id", getCurrentUserId() || "TEST");
  }
  if (init.body && !headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const request = { ...init, headers };
  const method = (init.method || "GET").toUpperCase();
  const retryableRead = method === "GET" || method === "HEAD" || method === "OPTIONS";
  const retryableStatuses = new Set([429, 502, 503, 504]);
  const retryDelays = [120, 360];

  for (let attempt = 0; ; attempt += 1) {
    try {
      const response = await fetch(apiUrl(path), request);
      if (
        !retryableRead ||
        !retryableStatuses.has(response.status) ||
        attempt >= retryDelays.length
      ) {
        return response;
      }
      await waitForRetry(response, retryDelays[attempt]);
    } catch (error) {
      if (!retryableRead || attempt >= retryDelays.length) throw error;
      await delay(retryDelays[attempt]);
    }
  }
}

async function waitForRetry(response: Response, fallbackMs: number): Promise<void> {
  const retryAfter = response.headers.get("Retry-After");
  const seconds = retryAfter ? Number(retryAfter) : Number.NaN;
  const milliseconds = Number.isFinite(seconds)
    ? Math.min(Math.max(seconds * 1000, 0), 2000)
    : fallbackMs;
  await delay(milliseconds);
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));
}

/** Patch global fetch once so existing components send X-User-Id to Control Plane. */
let patched = false;
export function installApiAuthFetch(): void {
  if (typeof window === "undefined" || patched) return;
  patched = true;
  const native = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const isApi =
      url.includes("127.0.0.1:8000") ||
      url.includes("localhost:8000") ||
      (typeof process !== "undefined" &&
        !!process.env.NEXT_PUBLIC_CONTROL_PLANE_URL &&
        url.startsWith(process.env.NEXT_PUBLIC_CONTROL_PLANE_URL));
    if (!isApi) return native(input, init);
    const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
    if (!headers.has("X-User-Id")) {
      headers.set("X-User-Id", getCurrentUserId() || "TEST");
    }
    return native(input, { ...init, headers });
  };
}
