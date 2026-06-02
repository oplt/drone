import { useQuery } from "@tanstack/react-query";
import { fetchWarehouseFlightReadiness } from "../api/warehouseFlightApi";

const READINESS_POLL_MS = 5000;

export function useWarehouseFlightReadiness(
  token: string | null,
  options?: { missionLoaded?: boolean; enabled?: boolean },
) {
  const enabled = Boolean(token) && (options?.enabled ?? true);
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
          ? READINESS_POLL_MS * 5
          : READINESS_POLL_MS
        : false,
    refetchIntervalInBackground: false,
    staleTime: 3_000,
    queryFn: () =>
      fetchWarehouseFlightReadiness(token as string, {
        missionLoaded: options?.missionLoaded,
      }),
  });
}
