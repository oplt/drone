import { httpRequest } from "../../../shared/api/httpClient";
import type { ManualCommandPhase, ManualFlightCommand } from "../types";

export type ManualControlRequest = {
  command: ManualFlightCommand;
  phase: ManualCommandPhase;
  source: "keyboard" | "button";
  flight_id?: string | null;
};

export async function sendManualControlCommand(
  payload: ManualControlRequest,
  token?: string | null,
): Promise<void> {
  await httpRequest("/telemetry/manual-control", {
    method: "POST",
    body: payload,
    token,
    skipUnauthorizedRedirect: true,
  });
}
