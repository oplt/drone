import { useQuery } from "@tanstack/react-query";
import { fetchWarehousePreflight } from "../api/warehousePreflightApi";
import {
  PREFLIGHT_SNAPSHOT_POLL_MS,
  PREFLIGHT_SNAPSHOT_STALE_MS,
} from "./preflightPolling";

export function useWarehousePreflightSnapshot(
  token: string | null,
  options?: {
    missionLoaded?: boolean;
    enabled?: boolean;
    /** Pause background snapshot polling while an explicit refresh run is active. */
    refreshRunning?: boolean;
    /** Poll GET snapshot on an interval (default off). */
    poll?: boolean;
  },
) {
  const missionLoaded = options?.missionLoaded ?? false;
  const enabled =
    Boolean(token) &&
    (options?.enabled ?? false) &&
    !(options?.refreshRunning ?? false);

  return useQuery({
    queryKey: ["warehouse-preflight", token, missionLoaded],
    enabled,
    staleTime: PREFLIGHT_SNAPSHOT_STALE_MS,
    refetchInterval: () => {
      if (!enabled || !options?.poll) return false;
      return document.hidden ? PREFLIGHT_SNAPSHOT_POLL_MS * 2 : PREFLIGHT_SNAPSHOT_POLL_MS;
    },
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    queryFn: () =>
      fetchWarehousePreflight(token as string, {
        missionLoaded,
      }),
  });
}
