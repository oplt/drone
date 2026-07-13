import { httpRequest } from "../../../shared/api/httpClient";
import type {
  IrrigationMissionSummary,
  IrrigationProcessingJob,
} from "../types/irrigation";

export async function fetchIrrigationMissionSummary(
  missionId: string,
  token?: string | null,
): Promise<IrrigationMissionSummary> {
  return httpRequest<IrrigationMissionSummary>(
    `/irrigation/missions/${encodeURIComponent(missionId)}/summary`,
    { token, skipUnauthorizedRedirect: true },
  );
}

export async function triggerIrrigationMissionProcessing(
  missionId: string,
  token?: string | null,
): Promise<IrrigationProcessingJob> {
  return httpRequest<IrrigationProcessingJob>(
    `/irrigation/missions/${encodeURIComponent(missionId)}/process-job`,
    { method: "POST", token, skipUnauthorizedRedirect: true },
  );
}
