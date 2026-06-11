import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getToken } from "../../../modules/session";
import {
  fetchMissionRuntime,
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
  type PrivatePatrolMissionStatus,
  type PatrolPreviewStats,
  type Waypoint,
} from "../types";

type StartMissionArgs = {
  token: string;
  payload: Record<string, unknown>;
  missionLabel: string;
  altToUse: number;
  repeatIntervalMinutes: number;
};

type RepeatMonitor = {
  args: StartMissionArgs;
  flightId: string;
  observedActive: boolean;
  finalStateChecked: boolean;
};

export function usePrivatePatrolMission({
  fieldBorder,
  mapEngine,
  terraDrawMode,
  addError,
  clearErrors,
  setPendingFlightId,
  showUiNotice,
  missionStatus,
  activeFlightId,
}: {
  fieldBorder: LonLat[] | null;
  mapEngine: MissionMapEngine;
  terraDrawMode: TerraDrawEditorMode;
  addError: (message: string) => void;
  clearErrors: () => void;
  setPendingFlightId: (id: string | null) => void;
  showUiNotice: (message: string, severity?: "success" | "info" | "warning" | "error") => void;
  missionStatus: PrivatePatrolMissionStatus | null;
  activeFlightId: string | null;
}) {
  const missionLaunchInFlightRef = useRef(false);
  const scheduledStartTimerRef = useRef<number | null>(null);
  const repeatStartTimerRef = useRef<number | null>(null);
  const startMissionNowRef = useRef<((args: StartMissionArgs) => Promise<void>) | null>(null);
  const repeatMonitorRef = useRef<RepeatMonitor | null>(null);
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const [eventLocation, setEventLocation] = useState<Waypoint | null>(null);
  const [alt, setAlt] = useState(30);
  const [altInput, setAltInput] = useState("30");
  const [name, setName] = useState("private-patrol-1");
  const [sending, setSending] = useState(false);
  const [preflightRun, setPreflightRun] = useState<PreflightRunResponse | null>(null);
  const [gridParams, setGridParams] = useState<PatrolGridParams>(DEFAULT_PATROL_GRID_PARAMS);
  const [drawMode, setDrawMode] = useState<DrawMode>("none");
  const [scheduledStartAt, setScheduledStartAt] = useState<number | null>(null);
  const [repeatStartAt, setRepeatStartAt] = useState<number | null>(null);
  const [repeatWaitingForCompletion, setRepeatWaitingForCompletion] = useState(false);

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
      start_after_minutes: gridParams.start_after_minutes,
      repeat_interval_minutes: gridParams.repeat_interval_minutes,
      camera_angle_deg: gridParams.camera_angle_deg,
      camera_overlap_pct: gridParams.camera_overlap_pct,
      max_segment_length_m: gridParams.max_segment_length_m,
      hover_time_s: gridParams.hover_time_s,
      camera_scan_yaw_deg: gridParams.camera_scan_yaw_deg,
      zoom_capture: gridParams.zoom_capture,
      return_to_start: gridParams.return_to_start,
      grid_spacing_m: gridParams.grid_spacing_m,
      grid_angle_deg: gridParams.grid_angle_deg,
      grid_pattern_mode: gridParams.grid_pattern_mode,
      grid_crosshatch_angle_offset_deg: gridParams.grid_crosshatch_angle_offset_deg,
      grid_lane_strategy: gridParams.grid_lane_strategy,
      grid_start_corner: gridParams.grid_start_corner,
      grid_row_stride: gridParams.grid_row_stride,
      grid_row_phase_m: gridParams.grid_row_phase_m,
      safety_inset_m: gridParams.safety_inset_m,
      trigger_type: gridParams.trigger_type,
      verification_loiter_s: gridParams.verification_loiter_s,
      verification_radius_m: gridParams.verification_radius_m,
      track_target: gridParams.track_target,
      auto_stream_video: gridParams.auto_stream_video,
      record_video_stream: gridParams.record_video_stream,
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

  const buildStartArgs = useCallback(
    ({
      token,
      altToUse,
      keyPointsLonLat,
      eventLocationLonLat,
    }: {
      token: string;
      altToUse: number;
      keyPointsLonLat: number[][];
      eventLocationLonLat: number[] | undefined;
    }): StartMissionArgs => {
      const taskType = gridParams.task_type;
      const repeatIntervalMinutes =
        taskType === "event_triggered_patrol"
          ? 0
          : Math.max(0, Math.min(1440, Math.round(gridParams.repeat_interval_minutes)));
      const missionLabel =
        taskType === "waypoint_patrol"
          ? "Waypoint Patrol"
          : taskType === "grid_surveillance"
            ? "Grid Surveillance"
            : taskType === "event_triggered_patrol"
              ? "Event-Triggered Patrol"
              : "Perimeter Patrol";
      const payload: Record<string, unknown> = {
        name: name.trim(),
        cruise_alt: altToUse,
        mission_type: "perimeter_patrol",
        private_patrol: {
          task_type: taskType,
          property_polygon_lonlat:
            taskType !== "waypoint_patrol" ? fieldBorder : undefined,
          key_points_lonlat:
            taskType === "waypoint_patrol" ? keyPointsLonLat : undefined,
          trigger_event_location_lonlat:
            taskType === "event_triggered_patrol"
              ? eventLocationLonLat
              : undefined,
          path_offset_m: gridParams.path_offset_m,
          direction: gridParams.direction,
          patrol_loops: gridParams.patrol_loops,
          speed_mps: gridParams.speed_mps,
          start_after_minutes: gridParams.start_after_minutes,
          repeat_interval_minutes: gridParams.repeat_interval_minutes,
          camera_angle_deg: gridParams.camera_angle_deg,
          camera_overlap_pct: gridParams.camera_overlap_pct,
          max_segment_length_m: gridParams.max_segment_length_m,
          hover_time_s: gridParams.hover_time_s,
          camera_scan_yaw_deg: gridParams.camera_scan_yaw_deg,
          zoom_capture: gridParams.zoom_capture,
          return_to_start: gridParams.return_to_start,
          grid_spacing_m: gridParams.grid_spacing_m,
          grid_angle_deg: gridParams.grid_angle_deg,
          grid_pattern_mode: gridParams.grid_pattern_mode,
          grid_crosshatch_angle_offset_deg: gridParams.grid_crosshatch_angle_offset_deg,
          grid_lane_strategy: gridParams.grid_lane_strategy,
          grid_start_corner: gridParams.grid_start_corner,
          grid_row_stride: gridParams.grid_row_stride,
          grid_row_phase_m: gridParams.grid_row_phase_m,
          safety_inset_m: gridParams.safety_inset_m,
          trigger_type: gridParams.trigger_type,
          verification_loiter_s: gridParams.verification_loiter_s,
          verification_radius_m: gridParams.verification_radius_m,
          track_target: gridParams.track_target,
          auto_stream_video: gridParams.auto_stream_video,
          record_video_stream: gridParams.record_video_stream,
          target_label:
            gridParams.target_label.trim().length > 0
              ? gridParams.target_label.trim()
              : undefined,
          ai_tasks: gridParams.ai_tasks,
        },
      };

      return {
        token,
        payload,
        missionLabel,
        altToUse,
        repeatIntervalMinutes,
      };
    },
    [fieldBorder, gridParams, name],
  );

  const startMissionNow = useCallback(
    async ({
      token,
      payload,
      missionLabel,
      altToUse,
      repeatIntervalMinutes,
    }: StartMissionArgs) => {
      if (missionLaunchInFlightRef.current) return;
      missionLaunchInFlightRef.current = true;
      setSending(true);
      clearErrors();

      try {
        const { preflight, mission: data } = await startMissionWithPreflight(payload, token);
        setPreflightRun(preflight);
        showUiNotice(
          `${missionLabel}: "${data.mission_name}" started. Tracking flight...${
            repeatIntervalMinutes > 0
              ? " Repeat interval starts after mission completion."
              : ""
          }`
        );

        setPendingFlightId(data.flight_id ?? null);
        setAlt(altToUse);
        setAltInput(String(altToUse));
        setScheduledStartAt(null);
        if (repeatStartTimerRef.current != null) {
          window.clearTimeout(repeatStartTimerRef.current);
          repeatStartTimerRef.current = null;
        }
        setRepeatStartAt(null);
        if (repeatIntervalMinutes > 0) {
          repeatMonitorRef.current = {
            args: { token, payload, missionLabel, altToUse, repeatIntervalMinutes },
            flightId: data.flight_id,
            observedActive: false,
            finalStateChecked: false,
          };
          setRepeatWaitingForCompletion(true);
        } else {
          repeatMonitorRef.current = null;
          setRepeatWaitingForCompletion(false);
        }
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Error creating flight plan";
        addError(message);
      } finally {
        setSending(false);
        missionLaunchInFlightRef.current = false;
      }
    }, [
      addError,
      clearErrors,
      setPendingFlightId,
      showUiNotice,
    ]);

  useEffect(() => {
    startMissionNowRef.current = startMissionNow;
  }, [startMissionNow]);

  const scheduleRepeatAfterCompletion = useCallback(
    (monitor: RepeatMonitor) => {
      const { args } = monitor;
      if (repeatStartTimerRef.current != null) {
        window.clearTimeout(repeatStartTimerRef.current);
      }
      const dueAt = Date.now() + args.repeatIntervalMinutes * 60_000;
      repeatStartTimerRef.current = window.setTimeout(() => {
        repeatStartTimerRef.current = null;
        setRepeatStartAt(null);
        void startMissionNowRef.current?.(args);
      }, args.repeatIntervalMinutes * 60_000);
      repeatMonitorRef.current = null;
      setRepeatWaitingForCompletion(false);
      setRepeatStartAt(dueAt);
      showUiNotice(
        `Property Patrol Mission completed. Next repeat starts in ${args.repeatIntervalMinutes} minute(s).`,
        "info",
      );
    },
    [showUiNotice],
  );

  useEffect(() => {
    const monitor = repeatMonitorRef.current;
    if (!monitor || repeatStartTimerRef.current != null) return;

    const lifecycle = missionStatus?.mission_lifecycle ?? null;
    const statusFlightId = lifecycle?.flight_id ?? missionStatus?.flight_id ?? null;
    const lifecycleState = lifecycle?.state ?? null;

    if (statusFlightId === monitor.flightId) {
      monitor.observedActive = true;
    }

    if (
      monitor.observedActive &&
      statusFlightId === monitor.flightId &&
      lifecycleState === "completed"
    ) {
      scheduleRepeatAfterCompletion(monitor);
      return;
    }

    if (
      monitor.observedActive &&
      statusFlightId === monitor.flightId &&
      (lifecycleState === "aborted" || lifecycleState === "failed")
    ) {
      repeatMonitorRef.current = null;
      setRepeatWaitingForCompletion(false);
      setRepeatStartAt(null);
      showUiNotice(
        `Property Patrol Mission ended as ${lifecycleState}; repeat disabled.`,
        "warning",
      );
      return;
    }

    const activeMissionGone = monitor.observedActive && !statusFlightId && !lifecycle;
    if (!activeMissionGone || monitor.finalStateChecked) return;

    monitor.finalStateChecked = true;
    let cancelled = false;
    void fetchMissionRuntime(monitor.flightId, monitor.args.token)
      .then((runtime) => {
        if (cancelled || repeatMonitorRef.current !== monitor) return;
        if (runtime.state === "completed") {
          scheduleRepeatAfterCompletion(monitor);
          return;
        }
        repeatMonitorRef.current = null;
        setRepeatWaitingForCompletion(false);
        setRepeatStartAt(null);
        showUiNotice(
          `Property Patrol Mission ended as ${runtime.state}; repeat disabled.`,
          "warning",
        );
      })
      .catch((err: unknown) => {
        if (cancelled || repeatMonitorRef.current !== monitor) return;
        repeatMonitorRef.current = null;
        setRepeatWaitingForCompletion(false);
        setRepeatStartAt(null);
        const message =
          err instanceof Error
            ? err.message
            : "Could not confirm completed mission state";
        addError(`Repeat disabled: ${message}`);
      });

    return () => {
      cancelled = true;
    };
  }, [
    activeFlightId,
    addError,
    missionStatus?.flight_id,
    missionStatus?.mission_lifecycle,
    scheduleRepeatAfterCompletion,
    showUiNotice,
  ]);

  const cancelScheduledStart = useCallback(() => {
    if (scheduledStartTimerRef.current != null) {
      window.clearTimeout(scheduledStartTimerRef.current);
      scheduledStartTimerRef.current = null;
    }
    if (repeatStartTimerRef.current != null) {
      window.clearTimeout(repeatStartTimerRef.current);
      repeatStartTimerRef.current = null;
    }
    repeatMonitorRef.current = null;
    setScheduledStartAt(null);
    setRepeatStartAt(null);
    setRepeatWaitingForCompletion(false);
    showUiNotice("Scheduled Property Patrol Mission start cancelled.", "info");
  }, [showUiNotice]);

  useEffect(() => {
    return () => {
      if (scheduledStartTimerRef.current != null) {
        window.clearTimeout(scheduledStartTimerRef.current);
      }
      if (repeatStartTimerRef.current != null) {
        window.clearTimeout(repeatStartTimerRef.current);
      }
      repeatMonitorRef.current = null;
    };
  }, []);

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

    const startAfterMinutes =
      gridParams.task_type === "event_triggered_patrol"
        ? 0
        : Math.max(0, Math.min(1440, Math.round(gridParams.start_after_minutes)));
    const startArgs = buildStartArgs({
      token,
      altToUse,
      keyPointsLonLat,
      eventLocationLonLat,
    });
    if (repeatStartTimerRef.current != null) {
      window.clearTimeout(repeatStartTimerRef.current);
      repeatStartTimerRef.current = null;
      setRepeatStartAt(null);
    }
    repeatMonitorRef.current = null;
    setRepeatWaitingForCompletion(false);
    if (startAfterMinutes > 0) {
      if (scheduledStartTimerRef.current != null) {
        window.clearTimeout(scheduledStartTimerRef.current);
      }
      const dueAt = Date.now() + startAfterMinutes * 60_000;
      scheduledStartTimerRef.current = window.setTimeout(() => {
        scheduledStartTimerRef.current = null;
        void startMissionNow(startArgs);
      }, startAfterMinutes * 60_000);
      setScheduledStartAt(dueAt);
      showUiNotice(
        `Property Patrol Mission scheduled to start in ${startAfterMinutes} minute(s).`,
        "info",
      );
      return;
    }

    await startMissionNow(startArgs);
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
    scheduledStartAt,
    repeatStartAt,
    repeatWaitingForCompletion,
    cancelScheduledStart,
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
