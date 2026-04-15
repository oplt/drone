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
  alwaysConnect = false,
}: {
  apiBase: string;
  onError: (msg: string) => void;
  getTokenFn?: () => string | null;
  /** When true, keep the WebSocket open whenever the drone is connected (skip flight/telemetry gates). */
  alwaysConnect?: boolean;
}) {
  const [pendingFlightId, setPendingFlightId] = useState<string | null>(null);
  const [latestWsMessage, setLatestWsMessage] = useState<any>(null);

  const { status: missionStatus, activeFlightId: polledActiveFlightId } =
    useMissionStatusPolling<TStatus>({
      apiBase,
      getToken: getTokenFn,
      onError,
      lifecycleMessage: latestWsMessage,
    });

  const activeFlightId = polledActiveFlightId ?? pendingFlightId;
  const wsEnabled = alwaysConnect
    ? Boolean(getTokenFn())
    : Boolean(
        missionStatus?.orchestrator?.drone_connected &&
          missionStatus?.telemetry?.running &&
          activeFlightId,
      );

  const { telemetry, isConnected: wsConnected, disconnect } = useTelemetryWebSocket({
    enabled: wsEnabled,
    onMessage: (msg) => {
      if (msg?.type === "mission_lifecycle") {
        setLatestWsMessage(msg);
      }
    },
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
