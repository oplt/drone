import { useQuery } from "@tanstack/react-query";

import {
  fetchWarehouseMappingStackStatus,
  type WarehouseMappingStackStatus,
} from "../api/warehouseMissionsApi";

type UseWarehouseMappingStackOptions = {
  enabled?: boolean;
  pollIntervalMs?: number;
  getToken: () => string | null;
};

export function useWarehouseMappingStack({
  enabled = true,
  pollIntervalMs = 5000,
  getToken,
}: UseWarehouseMappingStackOptions) {
  const token = getToken();
  const query = useQuery<WarehouseMappingStackStatus, Error>({
    queryKey: ["warehouse-mapping-stack", token],
    enabled: enabled && Boolean(token),
    queryFn: () => fetchWarehouseMappingStackStatus(token as string),
    staleTime: Math.min(pollIntervalMs, 5_000),
    refetchInterval: enabled ? pollIntervalMs : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });

  return {
    mappingStackStatus: query.data ?? null,
    loading: query.isLoading || query.isFetching,
    error: query.error?.message ?? null,
    refresh: query.refetch,
  };
}
