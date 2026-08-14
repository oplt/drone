export type DashboardAlertItem = {
  id: string;
  title: string;
  message: string;
  severity: "critical" | "high" | "medium" | "low" | "warning" | "info" | "error" | string;
  /** ISO timestamp used for severity-then-recency ordering. */
  triggeredAt?: string;
  onOpen?: () => void;
};

export const severityRank = (severity: string): number => {
  const n = String(severity || "").toLowerCase();
  if (n === "critical" || n === "error") return 0;
  if (n === "high") return 1;
  if (n === "medium" || n === "warning") return 2;
  if (n === "low" || n === "info") return 3;
  return 4;
};

export const toMuiSeverity = (
  severity: string,
): "error" | "warning" | "info" | "success" => {
  const n = String(severity || "").toLowerCase();
  if (n === "critical" || n === "high" || n === "error") return "error";
  if (n === "medium" || n === "warning") return "warning";
  if (n === "low" || n === "info") return "info";
  return "warning";
};

export function sortDashboardAlerts(items: DashboardAlertItem[]): DashboardAlertItem[] {
  return [...items].sort((a, b) => {
    const bySev = severityRank(a.severity) - severityRank(b.severity);
    if (bySev !== 0) return bySev;
    const aTime = a.triggeredAt ? new Date(a.triggeredAt).getTime() : 0;
    const bTime = b.triggeredAt ? new Date(b.triggeredAt).getTime() : 0;
    return bTime - aTime;
  });
}
