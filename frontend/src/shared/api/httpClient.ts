import { getApiBaseUrl, SIGN_IN_PATH } from "../../app/config/env";
import { emitAppLog } from "../logging";
import { ApiError } from "./apiError";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export type HttpRequestOptions = {
  method?: HttpMethod;
  body?: unknown | FormData;
  headers?: HeadersInit;
  signal?: AbortSignal;
  /** Legacy Bearer header for callers not yet on cookie-only auth. */
  token?: string | null;
  /** When true, a 401 does not trigger the global sign-in redirect. */
  skipUnauthorizedRedirect?: boolean;
  /** Retry transient fetch/network failures. Defaults to 2 for GET, 0 otherwise. */
  networkRetries?: number;
  /** Expected response statuses that should not emit app-log warnings/errors. */
  suppressErrorLogStatuses?: number[];
};

const inFlightGetRequests = new Map<string, Promise<unknown>>();
let refreshRequest: Promise<boolean> | null = null;

function createRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function resolveApiUrl(path: string): string {
  const base = getApiBaseUrl();
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${normalized}` : normalized;
}

function isAuthPath(url: string): boolean {
  try {
    const pathname = new URL(url, window.location.origin).pathname;
    return pathname.startsWith("/auth/");
  } catch {
    return url.includes("/auth/");
  }
}

function redirectToSignIn(): void {
  if (typeof window === "undefined") return;
  if (window.location.pathname === SIGN_IN_PATH) return;
  window.location.replace(SIGN_IN_PATH);
}

async function refreshAccessSession(): Promise<boolean> {
  if (refreshRequest) return refreshRequest;
  refreshRequest = (async () => {
    try {
      const response = await fetch(resolveApiUrl("/auth/refresh"), {
        method: "POST",
        credentials: "include",
      });
      return response.ok;
    } catch {
      return false;
    } finally {
      refreshRequest = null;
    }
  })();
  return refreshRequest;
}

/** session_present is a UI marker ("1"), not a JWT — never send it as Bearer auth. */
export function shouldAttachBearerToken(token: string | null | undefined): boolean {
  if (!token) return false;
  const trimmed = token.trim();
  if (!trimmed || trimmed === "1") return false;
  return trimmed.includes(".") || trimmed.startsWith("sk-");
}

export async function httpRequest<T>(
  path: string,
  options: HttpRequestOptions = {},
): Promise<T> {
  const url = resolveApiUrl(path);
  const method = options.method ?? "GET";
  const canDedupe =
    method === "GET" &&
    options.body == null &&
    options.signal == null &&
    options.headers == null;
  const dedupeKey = canDedupe
    ? `${url}|${options.token && shouldAttachBearerToken(options.token) ? options.token.trim() : ""}`
    : null;
  if (dedupeKey) {
    const pending = inFlightGetRequests.get(dedupeKey);
    if (pending) return pending as Promise<T>;
  }

  const request = performHttpRequestWithRetry<T>(url, method, options);
  if (!dedupeKey) return request;
  inFlightGetRequests.set(dedupeKey, request);
  try {
    return await request;
  } finally {
    inFlightGetRequests.delete(dedupeKey);
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const id = globalThis.setTimeout(resolve, ms);
    if (!signal) return;
    const onAbort = () => {
      globalThis.clearTimeout(id);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

async function performHttpRequestWithRetry<T>(
  url: string,
  method: HttpMethod,
  options: HttpRequestOptions,
): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  if (!headers.has("X-Request-ID")) {
    headers.set("X-Request-ID", createRequestId());
  }
  const requestId = headers.get("X-Request-ID") ?? undefined;
  const attemptOptions = { ...options, headers };
  const retryCount = options.networkRetries ?? (method === "GET" ? 2 : 0);
  let lastError: unknown;
  for (let attempt = 0; attempt <= retryCount; attempt += 1) {
    try {
      return await performHttpRequest<T>(url, method, attemptOptions);
    } catch (error) {
      if (error instanceof ApiError || isAbortError(error) || attempt >= retryCount) {
        if (!(error instanceof ApiError) && !isAbortError(error)) {
          emitAppLog({
            level: "error",
            source: "api",
            message: "Backend request could not be reached",
            requestId,
            details: {
              method,
              path: new URL(url, window.location.origin).pathname,
              error: error instanceof Error ? error.message : String(error),
            },
          });
        }
        throw error;
      }
      lastError = error;
      await sleep(250 * 2 ** attempt, attemptOptions.signal);
    }
  }
  throw lastError;
}

async function performHttpRequest<T>(
  url: string,
  method: HttpMethod,
  options: HttpRequestOptions,
): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  if (!headers.has("X-Request-ID")) {
    headers.set("X-Request-ID", createRequestId());
  }
  const requestId = headers.get("X-Request-ID") ?? undefined;

  const payload = options.body;
  const isFormData = payload instanceof FormData;
  if (payload != null && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (options.token && shouldAttachBearerToken(options.token)) {
    headers.set("Authorization", `Bearer ${options.token.trim()}`);
  }

  const requestBody: BodyInit | undefined =
    payload == null
      ? undefined
      : isFormData
        ? payload
        : JSON.stringify(payload);

  let response = await fetch(url, {
    method,
    headers,
    credentials: "include",
    signal: options.signal,
    body: requestBody,
  });

  if (response.status === 401 && !isAuthPath(url)) {
    const refreshed = await refreshAccessSession();
    if (refreshed) {
      response = await fetch(url, {
        method,
        headers,
        credentials: "include",
        signal: options.signal,
        body: requestBody,
      });
    } else if (!options.skipUnauthorizedRedirect) {
      redirectToSignIn();
    }
  }

  if (!response.ok) {
    const apiError = await ApiError.fromResponse(response);
    if (!options.suppressErrorLogStatuses?.includes(response.status)) {
      emitAppLog({
        level: response.status >= 500 ? "error" : "warn",
        source: "api",
        message: apiError.detail || apiError.message || "Backend request failed",
        requestId: apiError.requestId ?? requestId,
        details: {
          method,
          status: response.status,
          path: new URL(url, window.location.origin).pathname,
        },
      });
    }
    throw apiError;
  }

  if (response.status === 204) {
    return {} as T;
  }

  const text = await response.text();
  if (!text.trim()) {
    return {} as T;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (
    contentType.includes("text/html") ||
    text.trimStart().startsWith("<!doctype") ||
    text.trimStart().startsWith("<html")
  ) {
    throw new Error(
      `API route returned HTML instead of JSON: ${new URL(url, window.location.origin).pathname}`,
    );
  }

  return JSON.parse(text) as T;
}
