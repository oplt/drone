import { useCallback, useState } from "react";
import { getToken } from "../../session";
import {
  startMissionWithPreflight,
  type PreflightRunResponse,
} from "../../mission-runtime";
import type { AnimalFarmWaypoint } from "../animalFarmPageTypes";

type UseAnimalFarmMissionPlannerOptions = {
  addError: (message: string) => void;
  clearErrors: () => void;
  notify: (message: string, severity: "success" | "info" | "error") => void;
  setPendingFlightId: (flightId: string | null) => void;
  waypoints: AnimalFarmWaypoint[];
  clearWaypoints: () => void;
  setAlt: (value: number) => void;
  altInput: string;
  setAltInput: (value: string) => void;
};

export function useAnimalFarmMissionPlanner({
  addError,
  clearErrors,
  notify,
  setPendingFlightId,
  waypoints,
  clearWaypoints,
  setAlt,
  altInput,
  setAltInput,
}: UseAnimalFarmMissionPlannerOptions) {
  const [name, setName] = useState("field-plan-1");
  const [sending, setSending] = useState(false);
  const [preflightRun, setPreflightRun] = useState<PreflightRunResponse | null>(null);

  const sendMission = useCallback(async () => {
    const token = getToken();
    if (!token) {
      addError("Not authenticated");
      return;
    }
    if (waypoints.length < 2) {
      addError("Select at least 2 waypoints");
      return;
    }
    if (!name.trim()) {
      addError("Please enter a field plan name");
      return;
    }

    const altToUse = altInput === "" ? NaN : Number(altInput);
    if (!Number.isFinite(altToUse) || altToUse < 1 || altToUse > 500) {
      addError("Altitude must be between 1 and 500 meters");
      return;
    }

    setSending(true);
    clearErrors();

    try {
      const payload = {
        name: name.trim(),
        cruise_alt: altToUse,
        waypoints: waypoints.map((wp) => ({ lat: wp.lat, lon: wp.lon, alt: wp.alt })),
      };
      const { preflight, mission: data } = await startMissionWithPreflight(payload, token);
      setPreflightRun(preflight);
      notify(`Flight plan "${data.mission_name}" started. Tracking flight.`, "success");
      setPendingFlightId(data.flight_id ?? null);
      clearWaypoints();
      setAlt(altToUse);
      setAltInput(String(altToUse));
    } catch (error: unknown) {
      addError(error instanceof Error ? error.message : "Error creating flight plan");
    } finally {
      setSending(false);
    }
  }, [
    addError,
    altInput,
    clearErrors,
    clearWaypoints,
    name,
    notify,
    setAlt,
    setAltInput,
    setPendingFlightId,
    waypoints,
  ]);

  return {
    name,
    setName,
    sending,
    preflightRun,
    sendMission,
  };
}
