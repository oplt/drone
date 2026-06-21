import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { missionKeys } from "../../../app/config/queryKeys";
import { getSessionMarker } from "../../session";
import { fetchPreflightSettings } from "../api/preflightApi";
import { buildPreflightRows } from "../preflight/buildPreflightRows";
import { DEFAULT_PREFLIGHT_SETTINGS } from "../preflight/preflightUtils";
import type { PreflightRunResponse, TelemetrySnapshot } from "../types";

export function useMissionPreflightRows({
  missionType,
  preflightRun,
  telemetry,
  droneConnected,
}: {
  missionType: string;
  preflightRun: PreflightRunResponse | null;
  telemetry: TelemetrySnapshot | null;
  droneConnected?: boolean;
}) {
  const settingsQuery = useQuery({
    queryKey: missionKeys.preflightSettings(),
    queryFn: () => fetchPreflightSettings(getSessionMarker()),
    enabled: Boolean(getSessionMarker()),
  });

  const params = useMemo(
    () => ({ ...DEFAULT_PREFLIGHT_SETTINGS, ...(settingsQuery.data ?? {}) }),
    [settingsQuery.data],
  );

  const rowsByCategory = useMemo(
    () =>
      buildPreflightRows({
        missionType,
        params,
        telemetry,
        preflightRun,
        droneConnected,
      }),
    [droneConnected, missionType, params, preflightRun, telemetry],
  );

  return {
    rowsByCategory,
    loadingParams: settingsQuery.isLoading,
    paramsError:
      settingsQuery.error instanceof Error ? settingsQuery.error.message : null,
  };
}
