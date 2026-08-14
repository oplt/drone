import { useCallback, useEffect, useState } from "react";
import { getToken } from "../../session";
import {
  createLivestockTask,
  fetchHerds as loadHerds,
  fetchHerdLatestPositions,
  fetchHerdRiskAlerts,
  planLivestockTaskMission,
} from "../api/livestockApi";
import type { Herd, HerdAlert, HerdLatestPos, LivestockTaskType } from "../types";
import type { AnimalFarmPlannedRoute } from "../animalFarmPageTypes";

type UseAnimalFarmHerdsOptions = {
  addError: (message: string) => void;
  clearErrors: () => void;
  alt: number;
  onPlanReady: (plan: AnimalFarmPlannedRoute) => void;
};

export function useAnimalFarmHerds({
  addError,
  clearErrors,
  alt,
  onPlanReady,
}: UseAnimalFarmHerdsOptions) {
  const [herds, setHerds] = useState<Herd[]>([]);
  const [selectedHerdId, setSelectedHerdId] = useState<number | null>(null);
  const [latestPositions, setLatestPositions] = useState<HerdLatestPos[]>([]);
  const [herdAlerts, setHerdAlerts] = useState<HerdAlert[]>([]);
  const [loadingHerdOps, setLoadingHerdOps] = useState(false);
  const [collarIdForSearch, setCollarIdForSearch] = useState("");

  const fetchHerds = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    const data = await loadHerds(token);
    setHerds(data);
    if (!selectedHerdId && data.length > 0) setSelectedHerdId(data[0].id);
  }, [selectedHerdId]);

  const fetchLatestPositions = useCallback(async (herdId: number) => {
    const token = getToken();
    if (!token) return;
    setLatestPositions(await fetchHerdLatestPositions(herdId, token));
  }, []);

  const fetchRisk = useCallback(async (herdId: number) => {
    const token = getToken();
    if (!token) return;
    setHerdAlerts(await fetchHerdRiskAlerts(herdId, token));
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        await fetchHerds();
      } catch (error) {
        addError(error instanceof Error ? error.message : "Failed to load herds");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedHerdId) return;
    void (async () => {
      try {
        setLoadingHerdOps(true);
        await Promise.all([
          fetchLatestPositions(selectedHerdId),
          fetchRisk(selectedHerdId),
        ]);
      } catch (error) {
        addError(error instanceof Error ? error.message : "Failed to load herd ops data");
      } finally {
        setLoadingHerdOps(false);
      }
    })();
  }, [selectedHerdId, fetchLatestPositions, fetchRisk, addError]);

  const createTaskAndPlan = useCallback(
    async (type: LivestockTaskType) => {
      const token = getToken();
      if (!token) {
        addError("Not authenticated");
        return;
      }
      if (!selectedHerdId) {
        addError("Select a herd first");
        return;
      }

      try {
        setLoadingHerdOps(true);
        clearErrors();

        const params: Record<string, string> = {};
        if (type === "search_locate" && collarIdForSearch.trim()) {
          params.collar_id = collarIdForSearch.trim();
        }

        const task = await createLivestockTask(selectedHerdId, type, params, token);
        const plan = await planLivestockTaskMission(task.id, token);
        const mission = plan?.mission;
        const waypoints = (mission?.waypoints ?? []).map((wp) => ({
          lat: wp.lat,
          lon: wp.lon,
          alt: wp.alt ?? alt,
        }));

        if (waypoints.length === 0) {
          addError("Mission plan returned no waypoints");
          return;
        }

        onPlanReady({
          waypoints,
          name: `herd-${selectedHerdId}-${type}-${Date.now()}`,
          center: { lat: waypoints[0].lat, lng: waypoints[0].lon },
        });
      } catch (error) {
        addError(error instanceof Error ? error.message : "Task planning error");
      } finally {
        setLoadingHerdOps(false);
      }
    },
    [addError, alt, clearErrors, collarIdForSearch, onPlanReady, selectedHerdId],
  );

  return {
    herds,
    selectedHerdId,
    setSelectedHerdId,
    latestPositions,
    herdAlerts,
    loadingHerdOps,
    collarIdForSearch,
    setCollarIdForSearch,
    fetchLatestPositions,
    fetchRisk,
    createTaskAndPlan,
  };
}
