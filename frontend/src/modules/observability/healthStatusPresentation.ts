import type { HealthState } from "./types";

export function healthStatusTextColor(status: HealthState): string {
  switch (status) {
    case "healthy":
      return "success.main";
    case "degraded":
    case "down":
      return "error.main";
    case "unknown":
    default:
      return "text.disabled";
  }
}
