import { useMemo } from "react";
import useAnalyticsOverview from "../../dashboard";
import { deriveTelemetry, useTelemetryWebSocket } from "../../mission-runtime";
import { mapRecentFlightRows } from "../utils/fleetRecentFlightRows";

export function useFleetOverviewSession() {
  const { data, loading } = useAnalyticsOverview();
  const wsEnabled = Boolean(data?.system?.mavlink_connected);
  const { telemetry, isConnected } = useTelemetryWebSocket({ enabled: wsEnabled });

  const recentRows = useMemo(
    () => mapRecentFlightRows(data?.recent_flights ?? []),
    [data?.recent_flights],
  );

  const derived = deriveTelemetry(telemetry);
  const linkQualityRaw = telemetry?.link?.telemetry ?? telemetry?.link?.rc ?? null;
  const linkQuality =
    typeof linkQualityRaw === "number" ? linkQualityRaw : Number(linkQualityRaw);
  const batteryPct = derived.batteryPct;

  return {
    data,
    loading,
    system: data?.system,
    telemetry,
    isConnected,
    recentRows,
    derived,
    linkQuality,
    batteryPct,
  };
}

export type FleetOverviewSession = ReturnType<typeof useFleetOverviewSession>;
