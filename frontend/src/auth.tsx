// Tokens are in httpOnly cookies — no client-side token storage needed.
// These helpers exist for backward compatibility with any remaining callers.

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const SESSION_COOKIE_NAME = "session_present";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const needle = `${name}=`;
  const match = document.cookie
    .split(";")
    .map((entry) => entry.trim())
    .find((entry) => entry.startsWith(needle));
  return match ? decodeURIComponent(match.slice(needle.length)) : null;
}

/** @deprecated Tokens are now httpOnly cookies. Returns a session marker when present. */
export function getToken(): string | null {
  return readCookie(SESSION_COOKIE_NAME);
}

function clearSessionMarkerCookie(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${SESSION_COOKIE_NAME}=; Max-Age=0; path=/`;
}

/** @deprecated No-op. Tokens are managed server-side via cookies. */
export function setToken(_token: string): void {
  void _token;
  // Cookie state is managed server-side; the readable marker is set via Set-Cookie.
}

/** @deprecated No-op. Use logout() to clear cookies. */
export function clearToken(): void {
  clearSessionMarkerCookie();
}

export async function verifySession(): Promise<boolean> {
  try {
    const meRes = await fetch(`${API_BASE_URL}/auth/me`, {
      method: "GET",
      credentials: "include",
    });
    if (meRes.ok) return true;

    const refreshRes = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!refreshRes.ok) {
      clearSessionMarkerCookie();
      return false;
    }

    const meResAfterRefresh = await fetch(`${API_BASE_URL}/auth/me`, {
      method: "GET",
      credentials: "include",
    });
    if (!meResAfterRefresh.ok) {
      clearSessionMarkerCookie();
      return false;
    }
    return true;
  } catch {
    clearSessionMarkerCookie();
    return false;
  }
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } finally {
    clearSessionMarkerCookie();
  }
}

export async function refreshAccessToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    return res.ok;
  } catch {
    return false;
  }
}
