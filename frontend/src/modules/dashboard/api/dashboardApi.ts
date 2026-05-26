import { httpRequest } from "../../../shared/api/httpClient";
import type { AnalyticsOverview } from "../types";

export async function fetchAnalyticsOverview(
  signal?: AbortSignal,
): Promise<AnalyticsOverview> {
  return httpRequest<AnalyticsOverview>("/analytics/overview", {
    signal,
    skipUnauthorizedRedirect: true,
  });
}
