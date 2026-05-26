import { httpRequest } from "../../../shared/api/httpClient";

export async function connectDroneTelemetry(token?: string | null): Promise<void> {
  await httpRequest("/telemetry/connect", { method: "POST", token });
}
