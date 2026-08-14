import { useCallback, useContext, useState } from "react";
import { GoogleMapsContext, useDroneCenter, useUserLocation } from "../../maps";
import { useMissionCommandMetrics, useMissionWebsocketRuntime } from "../../mission-runtime";
import { useTaskPreflightCommandsDrawer } from "../../mission-workflow";
import { useMissionAltitudeInput } from "../../mission-workflow/hooks/useMissionAltitudeInput";
import { useErrors } from "../../../shared/hooks/useErrors";
import { useNotice } from "../../../shared/ui/NoticeContext";
import { getToken } from "../../session";
import {
  getControlledFlightApiBase,
  getControlledFlightMapConfig,
} from "../controlledFlightViewConstants";
import type { ControlledFlightMissionStatus } from "../controlledFlightViewTypes";
import { useControlledFlightDroneSession } from "./useControlledFlightDroneSession";
import { useControlledFlightMapSession } from "./useControlledFlightMapSession";
import { useControlledFlightMissionLauncher } from "./useControlledFlightMissionLauncher";
import { useControlledFlightRouteDrawing } from "./useControlledFlightRouteDrawing";
import { useControlledFlightVideoSession } from "./useControlledFlightVideoSession";

export function useControlledFlightPageSession() {
  const preflightCommandsDrawer = useTaskPreflightCommandsDrawer();
  const { errors, addError, clearErrors, dismissError } = useErrors();
  const { notify } = useNotice();
  const apiBase = getControlledFlightApiBase();
  const { apiKey, mapId } = getControlledFlightMapConfig();
  const videoToken = getToken();
  const { isLoaded, loadError } = useContext(GoogleMapsContext);
  const [lastMissionId, setLastMissionId] = useState<string | null>(null);
  const [droneManualConnected, setDroneManualConnected] = useState(false);

  const handleLocationError = useCallback(
    (error: GeolocationPositionError) => {
      const message = `Failed to get location: ${error.message}`;
      addError(message);
      return message;
    },
    [addError],
  );

  const { userCenter, loadingLocation } = useUserLocation({
    onLocationError: handleLocationError,
  });

  const altitude = useMissionAltitudeInput({ initialAltitude: 30, addError });

  const runtime = useMissionWebsocketRuntime<ControlledFlightMissionStatus>({
    apiBase,
    getTokenFn: getToken,
    onError: addError,
    alwaysConnect: droneManualConnected,
  });

  const droneCenter = useDroneCenter(runtime.telemetry);
  const commandMetrics = useMissionCommandMetrics(runtime.telemetry);

  const drawing = useControlledFlightRouteDrawing();
  const map = useControlledFlightMapSession({
    droneCenter,
    userCenter,
    wsConnected: runtime.wsConnected,
    mapId,
  });

  const missionLauncher = useControlledFlightMissionLauncher({
    addError,
    clearErrors,
    notify,
    setPendingFlightId: runtime.setPendingFlightId,
    setLastMissionId,
    setAlt: altitude.setAlt,
    altInput: altitude.altInput,
    setAltInput: altitude.setAltInput,
  });

  const droneSession = useControlledFlightDroneSession({
    addError,
    notify,
    droneManualConnected,
    setDroneManualConnected,
    missionStatus: runtime.missionStatus,
    activeFlightId: runtime.activeFlightId,
    lastMissionId,
    telemetry: runtime.telemetry,
    wsConnected: runtime.wsConnected,
    droneConnected: runtime.droneConnected,
    droneCenter,
  });

  const video = useControlledFlightVideoSession({
    apiBase,
    activeFlightId: runtime.activeFlightId,
    droneReady: droneSession.droneReady,
    addError,
  });

  return {
    apiBase,
    apiKey,
    mapId,
    videoToken,
    isLoaded,
    loadError,
    errors,
    addError,
    dismissError,
    clearErrors,
    preflightCommandsDrawer,
    altitude,
    runtime,
    droneCenter,
    commandMetrics,
    drawing,
    map,
    missionLauncher,
    droneSession,
    video,
    userCenter,
    loadingLocation,
  };
}

export type ControlledFlightPageSession = ReturnType<typeof useControlledFlightPageSession>;
