import { formatDuration, formatTime } from "../../dashboard/utils/dashboardFormatters";

type RecentFlightInput = {
  id: string | number;
  name: string;
  status?: string | null;
  duration_min: number | null;
  distance_km: number;
  telemetry_points: number;
  started_at?: string | null;
};

export type FleetRecentFlightRow = {
  id: string | number;
  plan: string;
  status: "Active" | "Paused" | "Interrupted" | "Failed" | "Completed";
  duration: string;
  distance: string;
  telemetry_points: number;
  started_at: string;
};

export function normalizeFleetFlightStatus(
  status: string | null | undefined,
): FleetRecentFlightRow["status"] {
  const normalizedStatus = String(status ?? "").toLowerCase();
  if (["active", "in_progress", "running"].includes(normalizedStatus)) return "Active";
  if (normalizedStatus === "paused") return "Paused";
  if (["interrupted", "aborted"].includes(normalizedStatus)) return "Interrupted";
  if (normalizedStatus === "failed") return "Failed";
  return "Completed";
}

export function mapRecentFlightRows(flights: RecentFlightInput[]): FleetRecentFlightRow[] {
  return flights.map((flight) => ({
    id: flight.id,
    plan: flight.name,
    status: normalizeFleetFlightStatus(flight.status),
    duration: formatDuration(flight.duration_min),
    distance: `${flight.distance_km.toFixed(1)} km`,
    telemetry_points: flight.telemetry_points,
    started_at: formatTime(flight.started_at),
  }));
}
