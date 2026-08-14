import { useEffect, useMemo, useState } from "react";
import { useAlertCenter } from "../../alerts";
import { deriveTelemetry, useTelemetryWebSocket } from "../../mission-runtime";
import type { DashboardStatCard } from "../types";
import type { DashboardAlertItem } from "../utils/dashboardAlerts";
import {
  deltaLabelFromSeries,
  formatDateLabel,
  formatDuration,
  formatNumber,
  formatTime,
  trendFromSeries,
} from "../utils/dashboardFormatters";
import { useAnalyticsOverview } from "./useAnalyticsOverview";

export function useDashboardOverviewModel() {
  const [nowSec, setNowSec] = useState(() => Math.round(Date.now() / 1000));
  const { data, loading, error, refresh } = useAnalyticsOverview();
  const { alerts: activeAlerts, setDrawerOpen, loadError: alertsLoadError, refresh: refreshAlerts } =
    useAlertCenter();
  const system = data?.system;
  const { telemetry, isConnected, lastPacketAt } = useTelemetryWebSocket({
    enabled: Boolean(system?.mavlink_connected),
  });

  useEffect(() => {
    const id = window.setInterval(() => setNowSec(Math.round(Date.now() / 1000)), 1000);
    return () => window.clearInterval(id);
  }, []);

  const summary = data?.summary;
  const trends = data?.trends;
  const labels = (trends?.days ?? []).map(formatDateLabel);
  const derived = useMemo(() => deriveTelemetry(telemetry), [telemetry]);

  const lastUpdateAge = useMemo(() => {
    if (lastPacketAt != null) {
      return Math.max(0, Math.round(nowSec - lastPacketAt / 1000));
    }
    if (system?.last_update && system.last_update > 0) {
      return Math.max(0, Math.round(nowSec - system.last_update));
    }
    return null;
  }, [lastPacketAt, nowSec, system]);

  const openAlerts = useMemo(
    () => setDrawerOpen.bind(null, true),
    [setDrawerOpen],
  );

  const alertItems = useMemo<DashboardAlertItem[]>(() => {
    if (activeAlerts.length > 0) {
      return activeAlerts.slice(0, 6).map((item) => ({
        id: String(item.id),
        title: item.title,
        message: item.message,
        severity: item.severity,
        triggeredAt: item.last_triggered_at,
        onOpen: openAlerts,
      }));
    }

    const fallback: DashboardAlertItem[] = [];
    if (system && !system.telemetry_running) {
      fallback.push({
        id: "telemetry-offline",
        title: "Telemetry stream offline",
        message: "Backend telemetry broadcaster is not running.",
        severity: "high",
        triggeredAt: new Date().toISOString(),
        onOpen: openAlerts,
      });
    }
    if (derived.batteryPct !== null && derived.batteryPct < 30) {
      fallback.push({
        id: "battery-low",
        title: "Battery health low",
        message: `Reserve at ${derived.batteryPct}%.`,
        severity: "critical",
        triggeredAt: new Date().toISOString(),
        onOpen: openAlerts,
      });
    }
    if (system && !isConnected) {
      fallback.push({
        id: "link-disconnected",
        title: "Live telemetry link disconnected",
        message: "WebSocket telemetry is not connected.",
        severity: "medium",
        triggeredAt: new Date().toISOString(),
        onOpen: openAlerts,
      });
    }
    return fallback;
  }, [activeAlerts, derived.batteryPct, isConnected, openAlerts, system]);

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

  return {
    data,
    loading,
    error,
    refresh,
    activeAlerts,
    alertItems,
    alertsLoadError,
    refreshAlerts,
    openAlertDrawer: openAlerts,
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
      mode: derived.modeShort !== "--" ? derived.modeShort : derived.mode,
      altitudeM: derived.relAltM ?? Number.NaN,
      speedMps: derived.groundSpeedMps ?? Number.NaN,
      batteryPct: derived.batteryPct,
      batteryShort: derived.batteryShort,
      satellites: derived.sats ?? Number.NaN,
      hdop: derived.hdop ?? Number.NaN,
      gpsQualityScore: derived.gpsQualityScore,
      gpsStrength: derived.gpsStrength,
      gpsShort: derived.gpsShort,
      speedShort: derived.speedShort,
      altShort: derived.altShort,
      modeShort: derived.modeShort,
    },
    formatNumber,
  };
}
