import { useEffect, useState } from "react";
import { getToken } from "../auth";
import useTelemetryWebSocket from "./useTelemetryWebsocket";
import { useMissionStatusPolling } from "./useMissionStatusPolling";

type MissionStatusLike = {
  orchestrator?: { drone_connected?: boolean };
  telemetry?: { running?: boolean };
};

export function useMissionWebsocketRuntime<TStatus extends MissionStatusLike>({
  apiBase,
  onError,
  getTokenFn = getToken,
}: {
  apiBase: string;
  onError: (msg: string) => void;
  getTokenFn?: () => string | null;
}) {
  const [pendingFlightId, setPendingFlightId] = useState<string | null>(null);

  const { status: missionStatus, activeFlightId: polledActiveFlightId } =
    useMissionStatusPolling<TStatus>({
      apiBase,
      getToken: getTokenFn,
      onError,
    });

  const activeFlightId = polledActiveFlightId ?? pendingFlightId;
  const wsEnabled = Boolean(
    missionStatus?.orchestrator?.drone_connected &&
      missionStatus?.telemetry?.running &&
      activeFlightId,
  );

  const { telemetry, isConnected: wsConnected, disconnect } = useTelemetryWebSocket({
    enabled: wsEnabled,
  });

  const droneConnected = Boolean(
    missionStatus?.orchestrator?.drone_connected || wsConnected,
  );

  useEffect(() => {
    if (polledActiveFlightId) {
      setPendingFlightId(null);
    }
  }, [polledActiveFlightId]);

  return {
    missionStatus,
    activeFlightId,
    setPendingFlightId,
    telemetry,
    wsConnected,
    disconnect,
    droneConnected,
  };
}
