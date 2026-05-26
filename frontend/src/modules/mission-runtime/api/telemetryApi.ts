import { httpRequest } from "../../../shared/api/httpClient";
import type { OpsHealthResponse } from "../types";

export async function fetchOpsHealth(token?: string | null): Promise<OpsHealthResponse> {
  return httpRequest<OpsHealthResponse>("/telemetry/ops-health", {
    token,
    skipUnauthorizedRedirect: true,
  });
}
