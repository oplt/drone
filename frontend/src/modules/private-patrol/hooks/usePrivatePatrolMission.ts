import { useCallback, useMemo, useRef, useState } from "react";
import { getToken } from "../../../modules/session";
import {
  startMissionWithPreflight,
  type PreflightRunResponse,
} from "../../mission-runtime";
import { usePatrolPreview } from "../../mission-planning";
import {
  CESIUM_MAX_SAFE_ZOOM,
  MAX_GRID_PREVIEW_WAYPOINTS,
  type DrawMode,
} from "../../mission-workflow";
import type { LonLat } from "../../fields";
import type { TerraDrawEditorMode } from "../../maps";
import type { MissionMapEngine } from "../../maps";
import {
  DEFAULT_PATROL_GRID_PARAMS,
  type PatrolGridParams,
  type PatrolPreviewStats,
  type Waypoint,
} from "../types";

export function usePrivatePatrolMission({
  fieldBorder,
  mapEngine,
  terraDrawMode,
  addError,
  clearErrors,
  setPendingFlightId,
  showUiNotice,
}: {
  fieldBorder: LonLat[] | null;
  mapEngine: MissionMapEngine;
  terraDrawMode: TerraDrawEditorMode;
  addError: (message: string) => void;
  clearErrors: () => void;
  setPendingFlightId: (id: string | null) => void;
  showUiNotice: (message: string, severity?: "success" | "info" | "warning" | "error") => void;
}) {
  const missionLaunchInFlightRef = useRef(false);
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const [eventLocation, setEventLocation] = useState<Waypoint | null>(null);
  const [alt, setAlt] = useState(30);
  const [altInput, setAltInput] = useState("30");
  const [name, setName] = useState("private-patrol-1");
  const [sending, setSending] = useState(false);
  const [preflightRun, setPreflightRun] = useState<PreflightRunResponse | null>(null);
  const [gridParams, setGridParams] = useState<PatrolGridParams>(DEFAULT_PATROL_GRID_PARAMS);
  const [drawMode, setDrawMode] = useState<DrawMode>("none");

  const isWaypointPatrol = gridParams.task_type === "waypoint_patrol";
  const isGridSurveillance = gridParams.task_type === "grid_surveillance";
  const isEventTriggeredPatrol = gridParams.task_type === "event_triggered_patrol";
  const hasPerimeterPolygon = Boolean(fieldBorder && fieldBorder.length >= 3);
  const hasWaypointKeyPoints = waypoints.length >= 2;
  const hasEventLocation = Boolean(eventLocation);
  const hasRequiredTaskGeometry = isWaypointPatrol
    ? hasWaypointKeyPoints
    : isEventTriggeredPatrol
      ? gridParams.trigger_type === "night_schedule"
        ? hasEventLocation || hasPerimeterPolygon
        : hasEventLocation
      : hasPerimeterPolygon;

  const patrolPreviewRequestBody = useMemo(() => {
    const keyPointsLonLat = waypoints.map((p) => [p.lon, p.lat]);
    const eventLocationLonLat = eventLocation
      ? [eventLocation.lon, eventLocation.lat]
      : undefined;
    if (
      (gridParams.task_type === "waypoint_patrol" && keyPointsLonLat.length < 2) ||
      (gridParams.task_type === "event_triggered_patrol" &&
        ((gridParams.trigger_type === "night_schedule" &&
          !eventLocationLonLat &&
          (!fieldBorder || fieldBorder.length < 3)) ||
          (gridParams.trigger_type !== "night_schedule" && !eventLocationLonLat))) ||
      (gridParams.task_type !== "waypoint_patrol" &&
        gridParams.task_type !== "event_triggered_patrol" &&
        (!fieldBorder || fieldBorder.length < 3))
    ) {
      return null;
    }

    return {
      task_type: gridParams.task_type,
      property_polygon_lonlat:
        gridParams.task_type !== "waypoint_patrol" ? fieldBorder : undefined,
      key_points_lonlat:
        gridParams.task_type === "waypoint_patrol" ? keyPointsLonLat : undefined,
      trigger_event_location_lonlat:
        gridParams.task_type === "event_triggered_patrol"
          ? eventLocationLonLat
          : undefined,
      cruise_alt: alt,
      path_offset_m: gridParams.path_offset_m,
      direction: gridParams.direction,
      patrol_loops: gridParams.patrol_loops,
      speed_mps: gridParams.speed_mps,
      camera_angle_deg: gridParams.camera_angle_deg,
      camera_overlap_pct: gridParams.camera_overlap_pct,
      max_segment_length_m: gridParams.max_segment_length_m,
      hover_time_s: gridParams.hover_time_s,
      camera_scan_yaw_deg: gridParams.camera_scan_yaw_deg,
      zoom_capture: gridParams.zoom_capture,
      return_to_start: gridParams.return_to_start,
      grid_spacing_m: gridParams.grid_spacing_m,
      grid_angle_deg: gridParams.grid_angle_deg,
      safety_inset_m: gridParams.safety_inset_m,
      trigger_type: gridParams.trigger_type,
      verification_loiter_s: gridParams.verification_loiter_s,
      verification_radius_m: gridParams.verification_radius_m,
      track_target: gridParams.track_target,
      auto_stream_video: gridParams.auto_stream_video,
      target_label:
        gridParams.target_label.trim().length > 0
          ? gridParams.target_label.trim()
          : undefined,
      ai_tasks: gridParams.ai_tasks,
    };
  }, [alt, eventLocation, fieldBorder, gridParams, waypoints]);

  const {
    waypoints: gridPreview,
    workLegMask: gridPreviewMask,
    stats: gridPreviewStats,
    error: gridPreviewError,
    loading: previewLoading,
  } = usePatrolPreview({
    enabled:
      mapEngine !== "google" ||
      terraDrawMode === "static" ||
      terraDrawMode === "select",
    requestBody: patrolPreviewRequestBody,
  });

  const gridPreviewTooDense =
    !!gridPreview && gridPreview.length > MAX_GRID_PREVIEW_WAYPOINTS;
  const patrolPreviewStats = gridPreviewStats as PatrolPreviewStats | null;

  const polylinePath = useMemo(
    () => waypoints.map((p) => ({ lat: p.lat, lng: p.lon })),
    [waypoints]
  );

  const gridPreviewPolylineGroups = useMemo(() => {
    const grouped = {
      work: [] as Array<Array<{ lat: number; lng: number }>>,
      turn: [] as Array<Array<{ lat: number; lng: number }>>,
    };

    if (!gridPreview || gridPreview.length < 2) {
      return grouped;
    }

    let currentKind: "work" | "turn" | null = null;
    let currentPath: Array<{ lat: number; lng: number }> = [];

    for (let i = 0; i < gridPreview.length - 1; i++) {
      const start = { lat: gridPreview[i].lat, lng: gridPreview[i].lon };
      const end = { lat: gridPreview[i + 1].lat, lng: gridPreview[i + 1].lon };
      const nextKind: "work" | "turn" = gridPreviewMask?.[i] === false ? "turn" : "work";

      if (currentKind !== nextKind) {
        if (currentPath.length >= 2 && currentKind) {
          grouped[currentKind].push(currentPath);
        }
        currentKind = nextKind;
        currentPath = [start, end];
        continue;
      }

      currentPath.push(end);
    }

    if (currentPath.length >= 2 && currentKind) {
      grouped[currentKind].push(currentPath);
    }

    return grouped;
  }, [gridPreview, gridPreviewMask]);

  const cesiumPlannedRoute = useMemo(() => {
    if (gridPreview && gridPreview.length >= 2) {
      return gridPreview.map((p) => [p.lon, p.lat] as LonLat);
    }
    if (isWaypointPatrol && waypoints.length >= 2) {
      return waypoints.map((p) => [p.lon, p.lat] as LonLat);
    }
    return null;
  }, [gridPreview, isWaypointPatrol, waypoints]);

  const handleAltitudeInputChange = (value: string) => {
    if (value === "") {
      setAltInput("");
      return;
    }
    if (!/^\d+$/.test(value)) return;
    setAltInput(value);
  };

  const normalizeAltitude = () => {
    if (altInput === "") {
      setAltInput(String(alt));
      return;
    }
    const num = Number(altInput);
    if (!Number.isFinite(num)) {
      setAltInput(String(alt));
      return;
    }
    if (num < 1 || num > 500) {
      addError("Altitude must be between 1 and 500 meters");
      return;
    }
    setAlt(num);
  };

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

    const keyPointsLonLat = waypoints.map((p) => [p.lon, p.lat]);
    const eventLocationLonLat = eventLocation
      ? [eventLocation.lon, eventLocation.lat]
      : undefined;
    if (
      gridParams.task_type !== "waypoint_patrol" &&
      gridParams.task_type !== "event_triggered_patrol" &&
      (!fieldBorder || fieldBorder.length < 3)
    ) {
      addError("Draw or select a property polygon before starting this mission");
      return;
    }
    if (gridParams.task_type === "waypoint_patrol" && keyPointsLonLat.length < 2) {
      addError("Add at least 2 key points before starting waypoint patrol");
      return;
    }
    if (gridParams.task_type === "event_triggered_patrol") {
      if (
        gridParams.trigger_type === "night_schedule" &&
        !eventLocationLonLat &&
        (!fieldBorder || fieldBorder.length < 3)
      ) {
        addError(
          "For night schedule trigger, set an event location point or draw/select a property polygon."
        );
        return;
      }
      if (gridParams.trigger_type !== "night_schedule" && !eventLocationLonLat) {
        addError("Set an event location point before starting event-triggered patrol.");
        return;
      }
    }
    if (gridPreview && gridPreview.length > MAX_GRID_PREVIEW_WAYPOINTS) {
      addError(
        `Patrol preview is too dense for safe execution (${gridPreview.length}/${MAX_GRID_PREVIEW_WAYPOINTS} waypoints). Increase segment length, reduce patrol loops, or split the property.`
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
        mission_type: "perimeter_patrol",
        private_patrol: {
          task_type: gridParams.task_type,
          property_polygon_lonlat:
            gridParams.task_type !== "waypoint_patrol" ? fieldBorder : undefined,
          key_points_lonlat:
            gridParams.task_type === "waypoint_patrol" ? keyPointsLonLat : undefined,
          trigger_event_location_lonlat:
            gridParams.task_type === "event_triggered_patrol"
              ? eventLocationLonLat
              : undefined,
          path_offset_m: gridParams.path_offset_m,
          direction: gridParams.direction,
          patrol_loops: gridParams.patrol_loops,
          speed_mps: gridParams.speed_mps,
          camera_angle_deg: gridParams.camera_angle_deg,
          camera_overlap_pct: gridParams.camera_overlap_pct,
          max_segment_length_m: gridParams.max_segment_length_m,
          hover_time_s: gridParams.hover_time_s,
          camera_scan_yaw_deg: gridParams.camera_scan_yaw_deg,
          zoom_capture: gridParams.zoom_capture,
          return_to_start: gridParams.return_to_start,
          grid_spacing_m: gridParams.grid_spacing_m,
          grid_angle_deg: gridParams.grid_angle_deg,
          safety_inset_m: gridParams.safety_inset_m,
          trigger_type: gridParams.trigger_type,
          verification_loiter_s: gridParams.verification_loiter_s,
          verification_radius_m: gridParams.verification_radius_m,
          track_target: gridParams.track_target,
          auto_stream_video: gridParams.auto_stream_video,
          target_label:
            gridParams.target_label.trim().length > 0
              ? gridParams.target_label.trim()
              : undefined,
          ai_tasks: gridParams.ai_tasks,
        },
      };

      const { preflight, mission: data } = await startMissionWithPreflight(payload, token);
      setPreflightRun(preflight);
      const missionLabel =
        gridParams.task_type === "waypoint_patrol"
          ? "Waypoint Patrol"
          : gridParams.task_type === "grid_surveillance"
            ? "Grid Surveillance"
            : gridParams.task_type === "event_triggered_patrol"
              ? "Event-Triggered Patrol"
              : "Perimeter Patrol";
      showUiNotice(
        `${missionLabel}: "${data.mission_name}" started. Tracking flight...`
      );

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
      if (gridParams.task_type === "waypoint_patrol") {
        setWaypoints((prev) => [...prev, { lat: p.lat, lon: p.lng, alt }]);
        return;
      }
      if (gridParams.task_type === "event_triggered_patrol") {
        setEventLocation({ lat: p.lat, lon: p.lng, alt });
      }
    },
    [alt, gridParams.task_type]
  );

  const cesiumZoomFor = useCallback(
    (mapZoom: number) => Math.min(mapZoom, CESIUM_MAX_SAFE_ZOOM),
    []
  );

  const mapHint = isWaypointPatrol
    ? "Add sensitive checkpoints (Gate, Parking, Warehouse doors, Roof), tune waypoint actions, and preview the verification route before launch."
    : isGridSurveillance
      ? "Draw a property polygon, configure coverage spacing, and preview the full-area surveillance grid before launch."
      : isEventTriggeredPatrol
        ? "Select a trigger profile, set an event location, and preview rapid verification flow (takeoff, goto, verify/track, stream)."
        : "Draw a property polygon, tune perimeter parameters, and preview the generated patrol route before launch.";

  return {
    waypoints,
    setWaypoints,
    eventLocation,
    setEventLocation,
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
    isWaypointPatrol,
    isGridSurveillance,
    isEventTriggeredPatrol,
    hasRequiredTaskGeometry,
    gridPreview,
    gridPreviewMask,
    patrolPreviewStats,
    gridPreviewError,
    previewLoading,
    gridPreviewTooDense,
    polylinePath,
    gridPreviewPolylineGroups,
    cesiumPlannedRoute,
    handleAltitudeInputChange,
    normalizeAltitude,
    sendMission,
    handleCesiumPick,
    cesiumZoomFor,
    mapHint,
  };
}
