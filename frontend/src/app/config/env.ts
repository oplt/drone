/** Resolved API origin for HTTP clients (empty string uses same-origin / Vite proxy). */
export function getApiBaseUrl(): string {
  const raw = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
  if (raw) {
    return raw.replace(/\/$/, "");
  }
  if (typeof window !== "undefined") {
    return "";
  }
  return "http://localhost:8000";
}

export const SESSION_COOKIE_NAME = "session_present";

export const SIGN_IN_PATH = "/signin";
