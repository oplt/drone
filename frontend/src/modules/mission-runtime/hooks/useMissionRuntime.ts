import { useEffect, useMemo, useState } from "react";
import { getSessionMarker } from "../../session";
import type {
  MissionLifecycleEvent,
  MissionRuntimeFacade,
  MissionStatusPayload,
  RuntimeConnectionState,
  TelemetrySocketMessage,
} from "../types";
import { useMissionStatusPolling } from "./useMissionStatusPolling";
import { useTelemetryStream } from "./useTelemetryStream";

export function useMissionRuntime<TStatus extends MissionStatusPayload>({
  onError,
  alwaysConnect = false,
}: {
  onError: (message: string) => void;
  alwaysConnect?: boolean;
}): MissionRuntimeFacade<TStatus> {
  const [pendingFlightId, setPendingFlightId] = useState<string | null>(null);
  const [latestLifecycleMessage, setLatestLifecycleMessage] =
    useState<MissionLifecycleEvent | null>(null);

  const { status: missionStatus, activeFlightId: polledActiveFlightId } =
    useMissionStatusPolling<TStatus>({
      lifecycleMessage: latestLifecycleMessage,
      onError,
    });

  const activeFlightId = polledActiveFlightId ?? pendingFlightId;
  const sessionPresent = Boolean(getSessionMarker());

  const wsEnabled = alwaysConnect
    ? sessionPresent
    : Boolean(
        missionStatus?.orchestrator?.drone_connected &&
          missionStatus?.telemetry?.running &&
          activeFlightId,
      );

  const {
    telemetry,
    isConnected: wsConnected,
    error: telemetryError,
    reconnect,
    disconnect,
    reconnectAttempt,
  } = useTelemetryStream({
    enabled: wsEnabled,
    onMessage: (message: TelemetrySocketMessage) => {
      if (message && typeof message === "object" && "type" in message && message.type === "mission_lifecycle") {
        setLatestLifecycleMessage(message as MissionLifecycleEvent);
      }
    },
  });

  const connection: RuntimeConnectionState = useMemo(() => {
    if (!wsEnabled) return "offline";
    if (wsConnected) return "online";
    if (telemetryError?.includes("Max reconnection")) return "offline";
    if (telemetryError || reconnectAttempt > 0) return "degraded";
    return "connecting";
  }, [reconnectAttempt, telemetryError, wsConnected, wsEnabled]);

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
    connection,
    wsConnected,
    droneConnected,
    telemetryError,
    reconnect,
    disconnect,
  };
}

export default useMissionRuntime;
