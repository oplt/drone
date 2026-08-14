import { useCallback, useContext, useState } from "react";
import { useNotice } from "../../../shared/ui/NoticeContext";
import { useErrors } from "../../../shared/hooks/useErrors";
import { frontendLogger } from "../../../shared/logging";
import type { LatLng } from "../../../shared/utils/extractLatLng";
import { GoogleMapsContext, useDroneCenter, useUserLocation } from "../../maps";
import {
  useMissionCommandMetrics,
  useMissionWebsocketRuntime,
} from "../../mission-runtime";
import { useTaskPreflightCommandsDrawer } from "../../mission-workflow";
import { useMissionAltitudeInput } from "../../mission-workflow/hooks/useMissionAltitudeInput";
import { getToken } from "../../session";
import {
  ANIMAL_FARM_DEFAULT_CENTER,
  getAnimalFarmApiBase,
  getAnimalFarmMapConfig,
} from "../animalFarmPageConstants";
import type { AnimalFarmMissionStatus, AnimalFarmPlannedRoute } from "../animalFarmPageTypes";
import { useAnimalFarmHerds } from "./useAnimalFarmHerds";
import { useAnimalFarmMapEngine } from "./useAnimalFarmMapEngine";
import { useAnimalFarmMapSession } from "./useAnimalFarmMapSession";
import { useAnimalFarmMissionPlanner } from "./useAnimalFarmMissionPlanner";
import { useAnimalFarmRouteDrawing } from "./useAnimalFarmRouteDrawing";
import { useAnimalFarmVideoSession } from "./useAnimalFarmVideoSession";

export function useAnimalFarmPageSession() {
  const { notify } = useNotice();
  const preflightCommandsDrawer = useTaskPreflightCommandsDrawer();
  const { errors, addError, clearErrors, dismissError } = useErrors();
  const [center, setCenter] = useState<LatLng>(ANIMAL_FARM_DEFAULT_CENTER);
  const apiBase = getAnimalFarmApiBase();
  const { apiKey, mapId } = getAnimalFarmMapConfig();
  const videoToken = getToken();
  const { isLoaded, loadError } = useContext(GoogleMapsContext);
  const mapEngineState = useAnimalFarmMapEngine();

  const handleLocationError = useCallback(
    (error: GeolocationPositionError) => {
      frontendLogger.error("frontend", "Error getting location", {
        message: error.message,
        code: error.code,
      });
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

  const runtime = useMissionWebsocketRuntime<AnimalFarmMissionStatus>({
    apiBase,
    getTokenFn: getToken,
    onError: addError,
    alwaysConnect: true,
  });

  const droneCenter = useDroneCenter(runtime.telemetry);
  const commandMetrics = useMissionCommandMetrics(runtime.telemetry);

  const drawing = useAnimalFarmRouteDrawing({
    addError,
    alt: altitude.alt,
    mapEngine: mapEngineState.mapEngine,
  });

  const map = useAnimalFarmMapSession({
    waypoints: drawing.waypoints,
    droneCenter,
    userCenter,
    wsConnected: runtime.wsConnected,
    center,
    isLoaded,
    ...mapEngineState,
  });

  const missionPlanner = useAnimalFarmMissionPlanner({
    addError,
    clearErrors,
    notify,
    setPendingFlightId: runtime.setPendingFlightId,
    waypoints: drawing.waypoints,
    clearWaypoints: drawing.clearWaypoints,
    setAlt: altitude.setAlt,
    altInput: altitude.altInput,
    setAltInput: altitude.setAltInput,
  });

  const handlePlanReady = useCallback(
    (plan: AnimalFarmPlannedRoute) => {
      drawing.applyPlannedRoute(plan);
      missionPlanner.setName(plan.name);
      setCenter(plan.center);
    },
    [drawing, missionPlanner],
  );

  const herds = useAnimalFarmHerds({
    addError,
    clearErrors,
    alt: altitude.alt,
    onPlanReady: handlePlanReady,
  });

  const video = useAnimalFarmVideoSession({
    apiBase,
    activeFlightId: runtime.activeFlightId,
    droneConnected: runtime.droneConnected,
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
    missionPlanner,
    herds,
    video,
    userCenter,
    loadingLocation,
  };
}

export type AnimalFarmPageSession = ReturnType<typeof useAnimalFarmPageSession>;
