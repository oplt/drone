import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { dashboardKeys } from "../../../app/config/queryKeys";
import { ApiError } from "../../../shared/api/apiError";
import { fetchAnalyticsOverview } from "../api/dashboardApi";
import type { AnalyticsOverview } from "../types";

function formatQueryError(error: unknown): string | null {
  if (!error) return null;
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Failed to load analytics";
}

export function useAnalyticsOverview(pollMs = 30_000) {
  const query = useQuery<AnalyticsOverview, unknown>({
    queryKey: dashboardKeys.analyticsOverview(),
    queryFn: ({ signal }) => fetchAnalyticsOverview(signal),
    refetchInterval: pollMs,
    refetchOnWindowFocus: true,
  });

  const hasData = useMemo(() => Boolean(query.data), [query.data]);

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: formatQueryError(query.error),
    hasData,
    refresh: () => {
      void query.refetch();
    },
  };
}

export default useAnalyticsOverview;
