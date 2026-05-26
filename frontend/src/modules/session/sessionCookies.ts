import { SESSION_COOKIE_NAME } from "../../app/config/env";

export function readSessionMarker(): string | null {
  if (typeof document === "undefined") return null;
  const needle = `${SESSION_COOKIE_NAME}=`;
  const match = document.cookie
    .split(";")
    .map((entry) => entry.trim())
    .find((entry) => entry.startsWith(needle));
  return match ? decodeURIComponent(match.slice(needle.length)) : null;
}

export function clearSessionMarker(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${SESSION_COOKIE_NAME}=; Max-Age=0; path=/`;
}

/** @deprecated Compatibility marker for legacy callers expecting a readable token. */
export function getSessionMarker(): string | null {
  return readSessionMarker();
}

/** @deprecated Server sets httpOnly cookies; marker is set via Set-Cookie when provided. */
export function setSessionMarker(_token: string): void {
  void _token;
}
