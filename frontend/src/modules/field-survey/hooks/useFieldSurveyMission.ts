import { useCallback, useMemo, useRef, useState } from "react";
import { getToken } from "../../../modules/session";
import {
  startMissionWithPreflight,
  type PreflightRunResponse,
} from "../../mission-runtime";
import { useGridPreview, createDefaultGridParams, type GridParams } from "../../mission-planning";
import {
  MAX_GRID_PREVIEW_WAYPOINTS,
  useMissionAltitudeInput,
  type Waypoint,
  type DrawMode,
} from "../../mission-workflow";
import { cesiumZoomForMapZoom } from "../../mission-workflow/utils/cesiumZoom";
import type { LonLat } from "../../fields";
import type { TerraDrawEditorMode } from "../../maps";
import type { MissionMapEngine } from "../../maps";

const DEFAULT_GRID_PARAMS = createDefaultGridParams();

export function useFieldSurveyMission({
  fieldBorder,
  mapEngine,
  terraDrawMode,
  addError,
  clearErrors,
  setPendingFlightId,
  setLastMissionId,
  onMissionStarted,
}: {
  fieldBorder: LonLat[] | null;
  mapEngine: MissionMapEngine;
  terraDrawMode: TerraDrawEditorMode;
  addError: (message: string) => void;
  clearErrors: () => void;
  setPendingFlightId: (id: string | null) => void;
  setLastMissionId: (id: string | null) => void;
  onMissionStarted: () => void;
}) {
  const missionLaunchInFlightRef = useRef(false);
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const {
    alt,
    altInput,
    setAlt,
    setAltInput,
    handleAltitudeInputChange,
    normalizeAltitude,
  } = useMissionAltitudeInput({ initialAltitude: 30, addError });
  const [name, setName] = useState("field-plan-1");
  const [sending, setSending] = useState(false);
  const [preflightRun, setPreflightRun] =
    useState<PreflightRunResponse | null>(null);
  const [gridParams, setGridParams] = useState<GridParams>(DEFAULT_GRID_PARAMS);
  const [drawMode, setDrawMode] = useState<DrawMode>("none");

  const {
    waypoints: gridPreview,
    workLegMask: gridPreviewMask,
    stats: gridPreviewStats,
    error: gridPreviewError,
    loading: previewLoading,
  } = useGridPreview({
    enabled:
      mapEngine !== "google" ||
      terraDrawMode === "static" ||
      terraDrawMode === "select",
    fieldBorder,
    gridParams,
  });

  const previewLegStats = useMemo(() => {
    if (!gridPreview || !gridPreviewMask) return null;
    const workLegs = gridPreviewMask.filter(Boolean).length;
    const transitLegs = gridPreviewMask.length - workLegs;
    return { workLegs, transitLegs };
  }, [gridPreview, gridPreviewMask]);

  const gridPreviewTooDense =
    !!gridPreview && gridPreview.length > MAX_GRID_PREVIEW_WAYPOINTS;

  const polylinePath = useMemo(
    () => waypoints.map((p) => ({ lat: p.lat, lng: p.lon })),
    [waypoints]
  );

  const cesiumPlannedRoute = useMemo(() => {
    if (gridPreview && gridPreview.length >= 2) {
      return gridPreview.map((p) => [p.lon, p.lat] as LonLat);
    }
    if (waypoints.length >= 2) {
      return waypoints.map((p) => [p.lon, p.lat] as LonLat);
    }
    return null;
  }, [gridPreview, waypoints]);

  const sendMission = async () => {
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

    if (!fieldBorder || fieldBorder.length < 3) {
      addError("Draw or select a field polygon before starting a grid survey");
      return;
    }
    if (gridPreview && gridPreview.length > MAX_GRID_PREVIEW_WAYPOINTS) {
      addError(
        `Grid preview is too dense for safe execution (${gridPreview.length}/${MAX_GRID_PREVIEW_WAYPOINTS} waypoints). Increase row spacing, increase row stride, or split the field.`
      );
      return;
    }
    if (gridPreviewError) {
      addError(gridPreviewError);
      return;
    }

    missionLaunchInFlightRef.current = true;
    setSending(true);
    clearErrors();

    try {
      const payload: Record<string, unknown> = {
        name: name.trim(),
        cruise_alt: altToUse,
        mission_type: "grid",
        grid: {
          field_polygon_lonlat: fieldBorder,
          row_spacing_m: gridParams.row_spacing_m,
          grid_angle_deg: gridParams.grid_angle_deg,
          slope_aware: gridParams.slope_aware,
          safety_inset_m: gridParams.safety_inset_m,
          terrain_follow: gridParams.terrain_follow,
          agl_m: gridParams.agl_m,
          pattern_mode: gridParams.pattern_mode,
          crosshatch_angle_offset_deg: gridParams.crosshatch_angle_offset_deg,
          start_corner: gridParams.start_corner,
          lane_strategy: gridParams.lane_strategy,
          row_stride: gridParams.row_stride,
          row_phase_m: gridParams.row_phase_m,
        },
      };

      const { preflight, mission: data } = await startMissionWithPreflight(payload, token);
      setPreflightRun(preflight);
      alert(`Grid Survey: "${data.mission_name}" started! Tracking flight...`);

      setPendingFlightId(data.flight_id ?? null);
      setLastMissionId(data.flight_id ?? null);
      onMissionStarted();

      setAlt(altToUse);
      setAltInput(String(altToUse));
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Error creating flight plan";
      addError(message);
    } finally {
      setSending(false);
      missionLaunchInFlightRef.current = false;
    }
  };

  const handleCesiumPick = useCallback(
    (p: { lat: number; lng: number }) => {
      setWaypoints((prev) => [...prev, { lat: p.lat, lon: p.lng, alt }]);
    },
    [alt]
  );

  const cesiumZoomFor = useCallback(
    (mapZoom: number) => cesiumZoomForMapZoom(mapZoom),
    [],
  );

  return {
    waypoints,
    setWaypoints,
    alt,
    altInput,
    name,
    setName,
    sending,
    preflightRun,
    gridParams,
    setGridParams,
    drawMode,
    setDrawMode,
    gridPreview,
    gridPreviewMask,
    gridPreviewStats,
    gridPreviewError,
    previewLoading,
    previewLegStats,
    gridPreviewTooDense,
    polylinePath,
    cesiumPlannedRoute,
    handleAltitudeInputChange,
    normalizeAltitude,
    sendMission,
    handleCesiumPick,
    cesiumZoomFor,
  };
}
