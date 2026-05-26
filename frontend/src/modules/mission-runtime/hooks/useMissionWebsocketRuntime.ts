import { useMissionRuntime } from "./useMissionRuntime";

type MissionStatusLike = {
  orchestrator?: { drone_connected?: boolean };
  telemetry?: { running?: boolean };
};

/** @deprecated Prefer useMissionRuntime. Kept for workflow modules during migration. */
export function useMissionWebsocketRuntime<TStatus extends MissionStatusLike>({
  apiBase,
  onError,
  getTokenFn,
  alwaysConnect = false,
}: {
  apiBase?: string;
  onError: (msg: string) => void;
  getTokenFn?: () => string | null;
  alwaysConnect?: boolean;
}) {
  void apiBase;
  void getTokenFn;

  const runtime = useMissionRuntime<TStatus>({ onError, alwaysConnect });

  return {
    missionStatus: runtime.missionStatus,
    activeFlightId: runtime.activeFlightId,
    setPendingFlightId: runtime.setPendingFlightId,
    telemetry: runtime.telemetry,
    wsConnected: runtime.wsConnected,
    disconnect: runtime.disconnect,
    droneConnected: runtime.droneConnected,
  };
}
