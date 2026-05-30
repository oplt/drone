import { getApiBaseUrl, SIGN_IN_PATH } from "../../app/config/env";
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
};

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
  const headers = new Headers(options.headers ?? {});

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

  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    credentials: "include",
    signal: options.signal,
    body: requestBody,
  });

  if (
    response.status === 401 &&
    !options.skipUnauthorizedRedirect &&
    !isAuthPath(url)
  ) {
    redirectToSignIn();
  }

  if (!response.ok) {
    throw await ApiError.fromResponse(response);
  }

  if (response.status === 204) {
    return {} as T;
  }

  const text = await response.text();
  if (!text.trim()) {
    return {} as T;
  }

  return JSON.parse(text) as T;
}
