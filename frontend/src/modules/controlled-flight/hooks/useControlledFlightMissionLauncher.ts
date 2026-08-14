import { useCallback, useRef, useState } from "react";
import {
  startMissionWithPreflight,
  type PreflightRunResponse,
} from "../../mission-runtime";
import { getToken } from "../../session";
import type { NoticeContextValue } from "../../../shared/ui/NoticeContext";

type UseControlledFlightMissionLauncherOptions = {
  addError: (message: string) => void;
  clearErrors: () => void;
  notify: NoticeContextValue["notify"];
  setPendingFlightId: (flightId: string | null) => void;
  setLastMissionId: (flightId: string | null) => void;
  setAlt: (alt: number) => void;
  altInput: string;
  setAltInput: (value: string) => void;
};

export function useControlledFlightMissionLauncher({
  addError,
  clearErrors,
  notify,
  setPendingFlightId,
  setLastMissionId,
  setAlt,
  altInput,
  setAltInput,
}: UseControlledFlightMissionLauncherOptions) {
  const missionLaunchInFlightRef = useRef(false);
  const [name, setName] = useState("Controlled Flight");
  const [sending, setSending] = useState(false);
  const [preflightRun, setPreflightRun] = useState<PreflightRunResponse | null>(null);

  const sendMission = useCallback(async () => {
    if (missionLaunchInFlightRef.current) return;
    const token = getToken();
    if (!token) {
      addError("Not authenticated");
      return;
    }
    if (!name.trim()) {
      addError("Please enter a mission name");
      return;
    }
    const altToUse = altInput === "" ? NaN : Number(altInput);
    if (!Number.isFinite(altToUse) || altToUse < 1 || altToUse > 500) {
      addError("Altitude must be between 1 and 500 meters");
      return;
    }

    missionLaunchInFlightRef.current = true;
    setSending(true);
    clearErrors();

    try {
      const payload: Record<string, unknown> = {
        name: name.trim(),
        cruise_alt: altToUse,
        mission_type: "controlled",
      };

      const { preflight, mission: data } = await startMissionWithPreflight(payload, token);
      setPreflightRun(preflight);
      setPendingFlightId(data.flight_id ?? null);
      setLastMissionId(data.flight_id ?? null);
      setAlt(altToUse);
      setAltInput(String(altToUse));
      notify(`Controlled flight "${data.mission_name ?? name.trim()}" started.`, {
        severity: "success",
        autoHideDuration: 9000,
        auditHref: data.flight_id ? `/dashboard/missions/${data.flight_id}/timeline` : undefined,
      });
    } catch (err: unknown) {
      addError(err instanceof Error ? err.message : "Error creating flight session");
    } finally {
      setSending(false);
      missionLaunchInFlightRef.current = false;
    }
  }, [
    addError,
    altInput,
    clearErrors,
    name,
    notify,
    setAlt,
    setAltInput,
    setLastMissionId,
    setPendingFlightId,
  ]);

  return {
    name,
    setName,
    sending,
    preflightRun,
    sendMission,
  };
}
