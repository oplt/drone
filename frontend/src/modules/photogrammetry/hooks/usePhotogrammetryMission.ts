import { useCallback, useMemo, useRef, useState } from "react";
import { getToken } from "../../../modules/session";
import {
  startMissionWithPreflight,
  type PreflightRunResponse,
} from "../../mission-runtime";
import { useGridPreview, createDefaultGridParams, type GridParams } from "../../mission-planning";
import {
  MAX_GRID_PREVIEW_WAYPOINTS,
  type Waypoint,
  type DrawMode,
} from "../../mission-workflow";
import { useMissionAltitudeInput } from "../../mission-workflow/hooks/useMissionAltitudeInput";
import { cesiumZoomForMapZoom } from "../../mission-workflow/utils/cesiumZoom";
import type { LonLat } from "../../fields";
import type { TerraDrawEditorMode, MissionMapEngine } from "../../maps";

export const PHOTOGRAMMETRY_ALT_MIN_M = 20;
export const PHOTOGRAMMETRY_ALT_MAX_M = 30;

export type PhotogrammetryProfile = {
  front_overlap_pct: number;
  side_overlap_pct: number;
  fixed_exposure: boolean;
  trigger_mode: "distance" | "time";
  trigger_distance_m: number;
  trigger_interval_s: number;
  speed_mps: number;
  positioning: "standard_gnss" | "rtk_ppk";
};

const DEFAULT_GRID_PARAMS = createDefaultGridParams({ agl_m: 25 });

const DEFAULT_PROFILE: PhotogrammetryProfile = {
  front_overlap_pct: 80,
  side_overlap_pct: 70,
  fixed_exposure: true,
  trigger_mode: "distance",
  trigger_distance_m: 2.5,
  trigger_interval_s: 1.0,
  speed_mps: 3.0,
  positioning: "rtk_ppk",
};

export function usePhotogrammetryMission({
  fieldBorder,
  mapEngine,
  terraDrawMode,
  addError,
  clearErrors,
  setPendingFlightId,
}: {
  fieldBorder: LonLat[] | null;
  mapEngine: MissionMapEngine;
  terraDrawMode: TerraDrawEditorMode;
  addError: (message: string) => void;
  clearErrors: () => void;
  setPendingFlightId: (id: string | null) => void;
}) {
  const missionLaunchInFlightRef = useRef(false);
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const {
    alt,
    setAlt,
    altInput,
    setAltInput,
    handleAltitudeInputChange,
    normalizeAltitude,
  } = useMissionAltitudeInput({
    initialAltitude: 25,
    minAltitude: PHOTOGRAMMETRY_ALT_MIN_M,
    maxAltitude: PHOTOGRAMMETRY_ALT_MAX_M,
    validationMessage: `Photogrammetry altitude must be between ${PHOTOGRAMMETRY_ALT_MIN_M} and ${PHOTOGRAMMETRY_ALT_MAX_M} meters`,
    addError,
  });
  const [name, setName] = useState("photogrammetry-plan-1");
  const [sending, setSending] = useState(false);
  const [preflightRun, setPreflightRun] =
    useState<PreflightRunResponse | null>(null);
  const [gridParams, setGridParams] = useState<GridParams>(DEFAULT_GRID_PARAMS);
  const [photogrammetryProfile, setPhotogrammetryProfile] =
    useState<PhotogrammetryProfile>(DEFAULT_PROFILE);
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
    if (
      !Number.isFinite(altToUse) ||
      altToUse < PHOTOGRAMMETRY_ALT_MIN_M ||
      altToUse > PHOTOGRAMMETRY_ALT_MAX_M
    ) {
      addError(
        `Photogrammetry altitude must be between ${PHOTOGRAMMETRY_ALT_MIN_M} and ${PHOTOGRAMMETRY_ALT_MAX_M} meters`
      );
      return;
    }

    if (!fieldBorder || fieldBorder.length < 3) {
      addError("Draw or select a field polygon before starting a photogrammetry mission");
      return;
    }
    if (gridPreview && gridPreview.length > MAX_GRID_PREVIEW_WAYPOINTS) {
      addError(
        `Photogrammetry coverage preview is too dense for safe execution (${gridPreview.length}/${MAX_GRID_PREVIEW_WAYPOINTS} waypoints). Increase row spacing, increase row stride, or split the field.`
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
        mission_profile: {
          type: "photogrammetry",
          altitude_m: altToUse,
          front_overlap_pct: photogrammetryProfile.front_overlap_pct,
          side_overlap_pct: photogrammetryProfile.side_overlap_pct,
          camera: {
            orientation: "nadir",
            fixed_exposure: photogrammetryProfile.fixed_exposure,
          },
          speed_mps: photogrammetryProfile.speed_mps,
          trigger:
            photogrammetryProfile.trigger_mode === "distance"
              ? {
                  mode: "distance",
                  distance_m: photogrammetryProfile.trigger_distance_m,
                }
              : {
                  mode: "time",
                  interval_s: photogrammetryProfile.trigger_interval_s,
                },
          accuracy: photogrammetryProfile.positioning,
        },
        processing: {
          service: "webodm",
          deployment: "fastapi_job_service",
          worker: {
            dedicated_machine_recommended: true,
            gpu_recommended: true,
            gpu_required: false,
          },
        },
        requested_artifacts: {
          orthomosaic: { required: true, format: "cog_geotiff" },
          dsm: { required: true, format: "cog_geotiff" },
          dtm: { required: false, format: "cog_geotiff" },
          textured_mesh: { required: true, format: "3d_tiles" },
          point_cloud: { required: false, format: "las_laz" },
        },
        grid: {
          field_polygon_lonlat: fieldBorder,
          row_spacing_m: gridParams.row_spacing_m,
          grid_angle_deg: gridParams.grid_angle_deg,
          slope_aware: gridParams.slope_aware,
          safety_inset_m: gridParams.safety_inset_m,
          terrain_follow: gridParams.terrain_follow,
          agl_m: altToUse,
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
      alert(`PhotoGrammetry Mission: "${data.mission_name}" started! Tracking flight...`);

      setPendingFlightId(data.flight_id ?? null);

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
    photogrammetryProfile,
    setPhotogrammetryProfile,
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
