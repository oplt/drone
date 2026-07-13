import { httpRequest } from "../../../shared/api/httpClient";
import { unwrapPage, type PageResponse } from "../../../shared/api/pagination";
import { ApiError } from "../../../shared/api/apiError";
import { ensureDroneConnectionForMissionStart } from "./telemetryConnectApi";
import type {
  MissionCommand,
  MissionCommandAuditResponse,
  MissionCommandResponse,
  MissionCreateResponse,
  MissionRuntimeResponse,
  MissionStateTransitionResponse,
  PreflightRunResponse,
} from "../types";

export async function runPreflight(
  missionPayload: Record<string, unknown>,
  token?: string | null,
): Promise<PreflightRunResponse> {
  const missionType =
    typeof missionPayload.mission_type === "string"
      ? missionPayload.mission_type
      : null;
  const flightEnvironment =
    typeof missionPayload.flight_environment === "string"
      ? missionPayload.flight_environment
      : null;
  await ensureDroneConnectionForMissionStart(
    token,
    missionType,
    flightEnvironment,
  );
  return httpRequest<PreflightRunResponse>("/tasks/preflight/run", {
    method: "POST",
    body: missionPayload,
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function createMission(
  missionPayload: Record<string, unknown> & { preflight_run_id: string },
  token?: string | null,
): Promise<MissionCreateResponse> {
  return httpRequest<MissionCreateResponse>("/tasks/missions", {
    method: "POST",
    body: missionPayload,
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function startMissionWithPreflight(
  missionPayload: Record<string, unknown>,
  token?: string | null,
): Promise<{
  preflight: PreflightRunResponse;
  mission: MissionCreateResponse;
}> {
  const missionType =
    typeof missionPayload.mission_type === "string"
      ? missionPayload.mission_type
      : null;
  const flightEnvironment =
    typeof missionPayload.flight_environment === "string"
      ? missionPayload.flight_environment
      : null;
  await ensureDroneConnectionForMissionStart(
    token,
    missionType,
    flightEnvironment,
  );
  const preflight = await runPreflight(missionPayload, token);
  if (!preflight.preflight_run_id) {
    throw new ApiError(400, "Preflight run did not return a run id.");
  }
  if (!preflight.can_start_mission) {
    const failed = preflight.report?.summary?.failed;
    const status = preflight.overall_status || "FAIL";
    throw new ApiError(
      400,
      typeof failed === "number"
        ? `Preflight ${status}. ${failed} checks failed; mission start blocked.`
        : `Preflight ${status}. Mission start blocked.`,
    );
  }

  const mission = await createMission(
    { ...missionPayload, preflight_run_id: preflight.preflight_run_id },
    token,
  );
  return { preflight, mission };
}

export async function fetchFlightStatus<TStatus = Record<string, unknown>>(
  token?: string | null,
): Promise<TStatus> {
  return httpRequest<TStatus>("/tasks/flight/status", {
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function fetchMissionRuntime(
  flightId: string,
  token?: string | null,
): Promise<MissionRuntimeResponse> {
  return httpRequest<MissionRuntimeResponse>(
    `/tasks/missions/${encodeURIComponent(flightId)}`,
    { token, skipUnauthorizedRedirect: true },
  );
}

export async function sendMissionCommand(
  flightId: string,
  command: MissionCommand,
  idempotencyKey: string,
  reason?: string | null,
  token?: string | null,
): Promise<MissionCommandResponse> {
  return httpRequest<MissionCommandResponse>(
    `/tasks/missions/${encodeURIComponent(flightId)}/commands/${command}`,
    {
      method: "POST",
      body: { idempotency_key: idempotencyKey, reason: reason ?? null },
      token,
      headers: { "Idempotency-Key": idempotencyKey },
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function fetchMissionCommandAudit(
  flightId: string,
  token?: string | null,
): Promise<MissionCommandAuditResponse[]> {
  const page = await httpRequest<PageResponse<MissionCommandAuditResponse>>(
    `/tasks/missions/${encodeURIComponent(flightId)}/commands`,
    { token, skipUnauthorizedRedirect: true },
  );
  return unwrapPage(page);
}

export async function fetchMissionStateTransitions(
  flightId: string,
  token?: string | null,
): Promise<MissionStateTransitionResponse[]> {
  const page = await httpRequest<PageResponse<MissionStateTransitionResponse>>(
    `/tasks/missions/${encodeURIComponent(flightId)}/transitions`,
    { token, skipUnauthorizedRedirect: true },
  );
  return unwrapPage(page);
}
