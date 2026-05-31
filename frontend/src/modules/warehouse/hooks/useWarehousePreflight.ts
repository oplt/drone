import { useQuery } from "@tanstack/react-query";
import { fetchWarehousePreflight } from "../api/warehousePreflightApi";

const PREFLIGHT_POLL_MS = 2000;

export function useWarehousePreflight(
  token: string | null,
  options?: { missionLoaded?: boolean; enabled?: boolean },
) {
  const enabled = Boolean(token) && (options?.enabled ?? false);
  return useQuery({
    queryKey: ["warehouse-preflight", token, options?.missionLoaded ?? false],
    enabled,
    refetchInterval: enabled ? PREFLIGHT_POLL_MS : false,
    queryFn: () =>
      fetchWarehousePreflight(token as string, {
        missionLoaded: options?.missionLoaded,
      }),
  });
}
