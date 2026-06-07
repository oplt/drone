import { httpRequest } from "../../../shared/api/httpClient";
import { ApiError } from "../../../shared/api/apiError";

export type TelemetryConnectResponse = {
  status?: string;
  drone?: boolean;
  telemetry_running?: boolean;
  flight_environment?: string;
};

export async function connectDroneTelemetry(
  token?: string | null,
  missionType?: string | null,
  flightEnvironment?: string | null,
): Promise<TelemetryConnectResponse> {
  const body =
    missionType || flightEnvironment
      ? {
          mission_type: missionType ?? undefined,
          flight_environment: flightEnvironment ?? undefined,
        }
      : undefined;
  return httpRequest<TelemetryConnectResponse>("/telemetry/connect", {
    method: "POST",
    body,
    token,
    skipUnauthorizedRedirect: true,
  });
}

/** Fail fast with a user-visible message when MAVLink/telemetry cannot be established. */
export async function ensureDroneConnectionForMissionStart(
  token?: string | null,
  missionType?: string | null,
  flightEnvironment?: string | null,
): Promise<TelemetryConnectResponse> {
  if (!token) {
    throw new ApiError(401, "Authentication required to connect to the drone.");
  }

  try {
    const result = await connectDroneTelemetry(token, missionType, flightEnvironment);
    if (!result.drone) {
      throw new ApiError(
        503,
        "Drone connection could not be established. Check that SITL or MAVLink is running, then try again.",
      );
    }
    return result;
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 503 && err.message.includes("Drone connection")) {
        throw err;
      }
      throw new ApiError(
        err.status,
        err.detail?.trim()
          ? `Drone connection could not be established: ${err.detail}`
          : err.message.includes("Drone connection")
            ? err.message
            : `Drone connection could not be established: ${err.message}`,
        err.detail,
        err.body,
        err.requestId,
      );
    }
    throw new ApiError(
      503,
      err instanceof Error
        ? `Drone connection could not be established: ${err.message}`
        : "Drone connection could not be established.",
    );
  }
}
