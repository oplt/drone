export function telemetryWebSocketUrl(): string {
  const apiBaseRaw = import.meta.env.VITE_API_BASE_URL as string | undefined;
  const apiBase = (apiBaseRaw?.trim() || "").replace(/\/$/, "");
  if (!apiBase) {
    return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/telemetry`;
  }
  if (apiBase.startsWith("http://") || apiBase.startsWith("https://")) {
    return `${apiBase.replace(/^http/, "ws")}/ws/telemetry`;
  }
  const prefix = apiBase.startsWith("/") ? apiBase : `/${apiBase}`;
  return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${prefix}/ws/telemetry`;
}
