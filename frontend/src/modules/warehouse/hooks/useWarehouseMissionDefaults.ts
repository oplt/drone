import { useCallback, useEffect, useState } from "react";
import { getToken } from "../../session";
import {
  fetchWarehouseMissionDefaults,
  updateWarehouseMissionDefaults,
} from "../api/warehouseMissionsApi";
import type { WarehouseMissionDefaultsResponse } from "../types/missions";
import {
  toWarehouseMissionDefaultsDraft,
  toWarehouseMissionDefaultsPayload,
  type WarehouseMissionDefaultsDraft,
  type WarehouseMissionDefaultsKey,
} from "../warehouseMissionDefaults";
import { toMessage } from "../warehousePageSupport";

type UseWarehouseMissionDefaultsOptions = {
  addError: (message: string) => void;
  notify: (message: string, severity: "success" | "info" | "error") => void;
};

export function useWarehouseMissionDefaults({
  addError,
  notify,
}: UseWarehouseMissionDefaultsOptions) {
  const [missionDefaultsDraft, setMissionDefaultsDraft] =
    useState<WarehouseMissionDefaultsDraft | null>(null);
  const [loadingMissionDefaults, setLoadingMissionDefaults] = useState(false);
  const [savingMissionDefaults, setSavingMissionDefaults] = useState(false);

  const loadMissionDefaults = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    setLoadingMissionDefaults(true);
    try {
      const defaults = await fetchWarehouseMissionDefaults(token);
      setMissionDefaultsDraft(toWarehouseMissionDefaultsDraft(defaults));
    } catch (error) {
      addError(
        `Warehouse mission defaults could not be loaded: ${toMessage(error)}`,
      );
    } finally {
      setLoadingMissionDefaults(false);
    }
  }, [addError]);

  useEffect(() => {
    void loadMissionDefaults();
  }, [loadMissionDefaults]);

  const handleMissionDefaultsDraftChange = useCallback(
    (key: WarehouseMissionDefaultsKey, value: string) => {
      setMissionDefaultsDraft((current) =>
        current ? { ...current, [key]: value } : current,
      );
    },
    [],
  );

  const handleUpdateMissionDefaults = useCallback(async () => {
    const token = getToken();
    if (!token) {
      addError("You must be authenticated to update warehouse mission defaults.");
      return;
    }
    if (!missionDefaultsDraft) {
      addError("Warehouse mission defaults are not available yet.");
      return;
    }

    let payload: WarehouseMissionDefaultsResponse;
    try {
      payload = toWarehouseMissionDefaultsPayload(missionDefaultsDraft);
    } catch (error) {
      addError(toMessage(error));
      return;
    }

    setSavingMissionDefaults(true);
    try {
      const saved = await updateWarehouseMissionDefaults(payload, token);
      setMissionDefaultsDraft(toWarehouseMissionDefaultsDraft(saved));
      notify("Warehouse mission defaults updated.", "success");
    } catch (error) {
      addError(
        `Warehouse mission defaults could not be updated: ${toMessage(error)}`,
      );
    } finally {
      setSavingMissionDefaults(false);
    }
  }, [addError, missionDefaultsDraft, notify]);

  return {
    missionDefaultsDraft,
    loadingMissionDefaults,
    savingMissionDefaults,
    handleMissionDefaultsDraftChange,
    handleUpdateMissionDefaults,
  };
}
