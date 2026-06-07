import { useQuery } from "@tanstack/react-query";
import { fetchWarehousePreflightRun } from "../api/warehousePreflightApi";
import {
  preflightRunElapsedMs,
  preflightRunPollIntervalMs,
} from "./preflightPolling";

export function useWarehousePreflightRun(
  token: string | null,
  runId: string | null,
  options?: { enabled?: boolean },
) {
  const enabled = (options?.enabled ?? true) && Boolean(token && runId);

  return useQuery({
    queryKey: ["warehouse-preflight-run", runId],
    enabled,
    queryFn: () => fetchWarehousePreflightRun(token as string, runId as string),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || status === "complete" || status === "failed") {
        return false;
      }
      const elapsed = preflightRunElapsedMs(query.state.data?.started_at);
      return preflightRunPollIntervalMs(elapsed);
    },
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    retry: (failureCount) => failureCount < 2,
  });
}
