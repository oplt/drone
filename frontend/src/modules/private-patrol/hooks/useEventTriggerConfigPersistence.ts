import { useEffect, useRef, useState } from "react";
import { getToken } from "../../session";
import {
  fetchEventTriggerConfig,
  saveEventTriggerConfig,
  type PatrolEventTriggerConfig,
  type PatrolSensorIntegration,
} from "../api/eventTriggerConfigApi";
import {
  DEFAULT_PATROL_GRID_PARAMS,
  type PatrolAiTask,
  type PatrolGridParams,
} from "../types";

type UseEventTriggerConfigPersistenceArgs = {
  selectedFieldId: number | null;
  gridParams: PatrolGridParams;
  setGridParams: React.Dispatch<React.SetStateAction<PatrolGridParams>>;
  cruiseAlt: number;
  setCruiseAlt: (alt: number) => void;
  setCruiseAltInput: (value: string) => void;
};

function aiTasksFromConfig(tasks: string[]): PatrolAiTask[] {
  const allowed = new Set<PatrolAiTask>(DEFAULT_PATROL_GRID_PARAMS.ai_tasks);
  return tasks.filter((task): task is PatrolAiTask => allowed.has(task as PatrolAiTask));
}

function buildSaveBody(
  fieldId: number,
  gridParams: PatrolGridParams,
  cruiseAlt: number,
) {
  return {
    field_id: fieldId,
    enabled: true,
    cruise_alt: cruiseAlt,
    speed_mps: gridParams.speed_mps,
    verification_loiter_s: gridParams.verification_loiter_s,
    verification_radius_m: gridParams.verification_radius_m,
    track_target: gridParams.track_target,
    target_label: gridParams.target_label.trim() || null,
    search_grid_spacing_m: gridParams.grid_spacing_m,
    search_grid_angle_deg: gridParams.grid_angle_deg,
    ai_tasks: gridParams.ai_tasks,
  };
}

export function useEventTriggerConfigPersistence({
  selectedFieldId,
  gridParams,
  setGridParams,
  cruiseAlt,
  setCruiseAlt,
  setCruiseAltInput,
}: UseEventTriggerConfigPersistenceArgs) {
  const [integration, setIntegration] = useState<PatrolSensorIntegration | null>(null);
  const [configReady, setConfigReady] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const skipNextSaveRef = useRef(false);
  const saveTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (selectedFieldId == null) {
      setIntegration(null);
      setConfigReady(false);
      return;
    }

    let cancelled = false;
    const token = getToken();
    setConfigReady(false);

    void fetchEventTriggerConfig(selectedFieldId, token)
      .then((config: PatrolEventTriggerConfig) => {
        if (cancelled) return;
        skipNextSaveRef.current = true;
        setIntegration(config.integration ?? null);
        setGridParams((prev) => ({
          ...prev,
          speed_mps: config.speed_mps,
          verification_loiter_s: config.verification_loiter_s,
          verification_radius_m: config.verification_radius_m,
          track_target: config.track_target,
          target_label: config.target_label ?? "",
          grid_spacing_m: config.search_grid_spacing_m,
          grid_angle_deg: config.search_grid_angle_deg,
          ai_tasks: aiTasksFromConfig(config.ai_tasks),
        }));
        setCruiseAlt(config.cruise_alt);
        setCruiseAltInput(String(config.cruise_alt));
        setConfigReady(true);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setSaveError(error instanceof Error ? error.message : "Failed to load event trigger setup");
        setConfigReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedFieldId, setCruiseAlt, setCruiseAltInput, setGridParams]);

  useEffect(() => {
    if (selectedFieldId == null || !configReady) return;
    if (skipNextSaveRef.current) {
      skipNextSaveRef.current = false;
      return;
    }

    if (saveTimerRef.current != null) {
      window.clearTimeout(saveTimerRef.current);
    }

    saveTimerRef.current = window.setTimeout(() => {
      const token = getToken();
      setSaving(true);
      setSaveError(null);
      void saveEventTriggerConfig(buildSaveBody(selectedFieldId, gridParams, cruiseAlt), token)
        .then((saved) => {
          setIntegration(saved.integration ?? null);
        })
        .catch((error: unknown) => {
          setSaveError(error instanceof Error ? error.message : "Failed to save event trigger setup");
        })
        .finally(() => {
          setSaving(false);
        });
    }, 800);

    return () => {
      if (saveTimerRef.current != null) {
        window.clearTimeout(saveTimerRef.current);
      }
    };
  }, [
    configReady,
    cruiseAlt,
    gridParams.ai_tasks,
    gridParams.grid_angle_deg,
    gridParams.grid_spacing_m,
    gridParams.speed_mps,
    gridParams.target_label,
    gridParams.track_target,
    gridParams.verification_loiter_s,
    gridParams.verification_radius_m,
    selectedFieldId,
  ]);

  return {
    eventTriggerIntegration: integration,
    eventTriggerConfigReady: configReady,
    eventTriggerSaving: saving,
    eventTriggerSaveError: saveError,
  };
}
