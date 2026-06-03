import { useMemo, useState } from "react";
import { useAlertCenter } from "../../alerts";
import { useTelemetryWebSocket } from "../../mission-runtime";
import type { DashboardStatCard } from "../types";
import {
  deltaLabelFromSeries,
  formatDateLabel,
  formatDuration,
  formatNumber,
  formatTime,
  trendFromSeries,
} from "../utils/dashboardFormatters";
import { useAnalyticsOverview } from "./useAnalyticsOverview";

const toNumber = (value: unknown) =>
  typeof value === "number" ? value : Number(value);

export function useDashboardOverviewModel() {
  const [nowSec] = useState(() => Math.round(Date.now() / 1000));
  const { data, loading, error, refresh } = useAnalyticsOverview();
  const { alerts: activeAlerts } = useAlertCenter();
  const system = data?.system;
  const { telemetry, isConnected } = useTelemetryWebSocket({
    enabled: Boolean(system?.mavlink_connected),
  });

  const summary = data?.summary;
  const trends = data?.trends;
  const labels = (trends?.days ?? []).map(formatDateLabel);
  const lastUpdateAge =
    system?.last_update && system.last_update > 0
      ? Math.max(0, Math.round(nowSec - system.last_update))
      : null;

  const statCards = useMemo<DashboardStatCard[]>(() => {
    const flightCounts = trends?.flight_counts ?? [];
    const telemetryCounts = trends?.telemetry_counts ?? [];
    const flightHours = trends?.flight_hours ?? [];
    return [
      {
        title: "Active field flights",
        value: formatNumber(summary?.active_flights),
        interval: "Right now",
        trend: trendFromSeries(flightCounts),
        deltaLabel: deltaLabelFromSeries(flightCounts),
        data: flightCounts,
        labels,
        tooltip:
          "Flights currently active or recently running in mission control.",
      },
      {
        title: "Survey hours",
        value: formatNumber(summary?.flight_hours_7d, "h"),
        interval: "Last 7 days",
        trend: trendFromSeries(flightHours),
        deltaLabel: deltaLabelFromSeries(flightHours),
        data: flightHours,
        labels,
        tooltip: "Total survey flight time across the last seven days.",
      },
      {
        title: "Telemetry frames",
        value: formatNumber(summary?.telemetry_24h),
        interval: "Last 24 hours",
        trend: trendFromSeries(telemetryCounts),
        deltaLabel: deltaLabelFromSeries(telemetryCounts),
        data: telemetryCounts,
        labels,
        tooltip: "Telemetry samples received in the last 24 hours.",
      },
      {
        title: "Avg battery health",
        value:
          summary?.avg_battery_24h != null
            ? `${summary.avg_battery_24h}%`
            : "--",
        interval: "Last 24 hours",
        trend:
          summary?.avg_battery_24h != null && summary.avg_battery_24h < 40
            ? "down"
            : "neutral",
        data: [],
        tooltip: "Average battery reserve reported over the last 24 hours.",
      },
    ];
  }, [labels, summary, trends]);

  const recentRows = useMemo(
    () =>
      (data?.recent_flights ?? []).map((flight) => {
        const status = String(flight.status ?? "").toLowerCase();
        return {
          id: flight.id,
          plan: flight.name,
          status: ["active", "in_progress", "running"].includes(status)
            ? "Active"
            : status === "paused"
              ? "Paused"
              : ["interrupted", "aborted"].includes(status)
                ? "Interrupted"
                : status === "failed"
                  ? "Failed"
                  : "Completed",
          duration: formatDuration(flight.duration_min),
          distance: `${flight.distance_km.toFixed(1)} km`,
          telemetry_points: flight.telemetry_points,
          started_at: formatTime(flight.started_at),
        };
      }),
    [data?.recent_flights],
  );

  const telemetryBattery = toNumber(
    telemetry?.battery?.remaining ?? telemetry?.battery_remaining,
  );
  const batteryPct =
    Number.isFinite(telemetryBattery) && telemetryBattery >= 0
      ? telemetryBattery
      : null;
  const alertItems =
    activeAlerts.length > 0
      ? activeAlerts.slice(0, 4).map((item) => `${item.title}: ${item.message}`)
      : ([
          system && !system.telemetry_running
            ? "Telemetry stream is offline."
            : null,
          batteryPct !== null && batteryPct < 30
            ? `Battery health low (${Math.round(batteryPct)}%).`
            : null,
          system && !isConnected ? "Live telemetry link disconnected." : null,
        ].filter(Boolean) as string[]);

  return {
    data,
    loading,
    error,
    refresh,
    activeAlerts,
    alertItems,
    system,
    summary,
    trends,
    labels,
    statCards,
    recentRows,
    showInitialSkeleton: loading && !data,
    lastUpdateAge,
    telemetry: {
      isConnected,
      mode: String(telemetry?.mode ?? telemetry?.status?.mode ?? "UNKNOWN"),
      altitudeM: toNumber(
        telemetry?.position?.relative_alt ??
          telemetry?.position?.relative_altitude,
      ),
      speedMps: toNumber(
        telemetry?.status?.groundspeed ?? telemetry?.groundspeed,
      ),
      batteryPct,
      satellites: toNumber(
        telemetry?.gps?.satellites ?? telemetry?.gps?.satellite_count,
      ),
      hdop: toNumber(telemetry?.gps?.hdop),
    },
    formatNumber,
  };
}
