import { httpRequest } from "../../../shared/api/httpClient";
import type {
  IrrigationMissionSummary,
  IrrigationProcessedFieldLayer,
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
): Promise<IrrigationProcessedFieldLayer> {
  return httpRequest<IrrigationProcessedFieldLayer>(
    `/irrigation/missions/${encodeURIComponent(missionId)}/process`,
    { method: "POST", token, skipUnauthorizedRedirect: true },
  );
}
