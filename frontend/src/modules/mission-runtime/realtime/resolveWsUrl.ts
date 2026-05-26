import { getApiBaseUrl } from "../../../app/config/env";

export function resolveTelemetryWebSocketUrl(): string {
  const apiBase = getApiBaseUrl();
  let wsBase: string;

  if (!apiBase) {
    wsBase = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  } else if (apiBase.startsWith("http://") || apiBase.startsWith("https://")) {
    wsBase = apiBase.replace(/^http/, "ws");
  } else if (apiBase.startsWith("/")) {
    wsBase = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${apiBase}`;
  } else {
    wsBase = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/${apiBase}`;
  }

  return `${wsBase}/ws/telemetry`;
}
