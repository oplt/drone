import { useQuery } from "@tanstack/react-query";
import { fetchWarehouseFlightReadiness } from "../api/warehouseFlightApi";
import { FLIGHT_READINESS_POLL_MS } from "./preflightPolling";

export function useWarehouseFlightReadiness(
  token: string | null,
  options?: {
    missionLoaded?: boolean;
    enabled?: boolean;
    /** Pause polling while an explicit preflight refresh owns bridge probes. */
    preflightRunning?: boolean;
  },
) {
  const enabled =
    Boolean(token) &&
    (options?.enabled ?? true) &&
    !(options?.preflightRunning ?? false);
  return useQuery({
    queryKey: [
      "warehouse-flight-readiness",
      token,
      options?.missionLoaded ?? false,
    ],
    enabled,
    refetchInterval: () =>
      enabled
        ? document.hidden
          ? FLIGHT_READINESS_POLL_MS * 2
          : FLIGHT_READINESS_POLL_MS
        : false,
    refetchIntervalInBackground: false,
    staleTime: 6_000,
    queryFn: () =>
      fetchWarehouseFlightReadiness(token as string, {
        missionLoaded: options?.missionLoaded,
      }),
  });
}
