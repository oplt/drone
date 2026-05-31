import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  CircularProgress,
  InputAdornment,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";
import ExploreRoundedIcon from "@mui/icons-material/ExploreRounded";
import Header from "../../../shared/layout/WorkflowHeader";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { ApiError } from "../../../shared/api/apiError";
import { ErrorAlerts } from "../../../shared/ui/ErrorAlerts";
import {
  MissionCommandPanel,
  MissionPreflightPanel,
  MissionStatusChips,
  MissionVideoPanel,
  useAutoStartVideo,
  useMissionWebsocketRuntime,
  type MissionLifecycleState,
  type PreflightRunResponse,
} from "../../mission-runtime";
import {
  TaskPreflightCommandsDrawer,
  useTaskPreflightCommandsDrawer,
} from "../../mission-workflow";
import { getToken } from "../../session";
import { useErrors } from "../../../shared/hooks/useErrors";
import {
  fetchWarehouseMissionDefaults,
  listWarehouseScannedMaps,
  startWarehouseScan,
  updateWarehouseMissionDefaults,
  deleteWarehouseScannedMap,
} from "../api/warehouseMissionsApi";
import type {
  WarehouseMissionDefaultsResponse,
  WarehouseMissionLaunchResponse,
  WarehouseScannedMapResponse,
} from "../types/missions";
import {
  getWarehouseMapId,
  getWarehouseName,
  selectScannedMap,
} from "../scannedMapSelectors";
import {
  createWarehouseMap,
  createWarehouseSensorRig,
  deleteWarehouseMap,
  deleteWarehouseSensorRig,
  fetchWarehouseSensorRigHealth,
  listWarehouseSensorRigs,
  listWarehouseMaps,
  updateWarehouseSensorRigCalibration,
} from "../api/warehouseMapsApi";
import type { WarehouseMapOut, WarehouseSensorRig, WarehouseSensorRigHealth } from "../types";
import {
  WarehouseMappingHealthPanel,
  type WarehouseMappingRuntimeStatus,
} from "../components/WarehouseMappingHealthPanel";
import { WarehouseDrawerSection } from "../components/WarehouseDrawerSection";
import { WarehouseDockPanel } from "../components/WarehouseDockPanel";
import { WarehouseExplorationPanel } from "../components/WarehouseExplorationPanel";
import { WarehouseManualMappingPanel } from "../components/WarehouseManualMappingPanel";
import { WarehouseMapQualityPanel } from "../components/WarehouseMapQualityPanel";
import { WarehouseScanViewer } from "../components/WarehouseScanViewer";

type CreateMapForm = {
  name: string;
  width_m: string;
  length_m: string;
};

type SensorRigForm = {
  name: string;
  camera_model: string;
  stereo_baseline_m: string;
  intrinsics_url: string;
  extrinsics_url: string;
  firmware_version: string;
  isaac_ros_version: string;
};

type WarehouseStartErrorBody = {
  detail?: {
    message?: string;
    preflight?: PreflightRunResponse;
    readiness?: Record<string, unknown>;
    missing_required_topics?: string[];
    missing_nvblox_topics?: string[];
    suggested_actions?: string[];
  };
  error?: {
    message?: string;
    details?: {
      message?: string;
      preflight?: PreflightRunResponse;
      readiness?: Record<string, unknown>;
      missing_required_topics?: string[];
      missing_nvblox_topics?: string[];
      suggested_actions?: string[];
    };
  };
};

type WarehouseMissionStatus = {
  flight_id?: string;
  mission_name?: string;
  telemetry?: {
    running?: boolean;
    active_connections?: number;
    has_position_data?: boolean;
    position?: {
      lat?: number;
      lon?: number;
      alt?: number;
    };
  };
  orchestrator?: {
    drone_connected?: boolean;
  };
  mission_lifecycle?: {
    flight_id?: string | null;
    state?: MissionLifecycleState;
    mission_name?: string;
    mission_type?: string;
    updated_at?: number;
    last_error?: string | null;
  } | null;
  command_capabilities?: {
    pause?: boolean;
    resume?: boolean;
    abort?: boolean;
  } | null;
  warehouse_mapping?: WarehouseMappingRuntimeStatus | null;
};

const VIDEO_RETRY_DELAY_MS = 5000;
const SCANNED_MAP_REFRESH_MS = 30000;

const COMPACT_FIELD_SX = {
  minWidth: 0,
  "& .MuiInputBase-input": { px: 0.75, py: 0.75 },
  "& .MuiInputAdornment-root": { ml: 0, mr: 0.25 },
  "& .MuiInputAdornment-root .MuiTypography-root": { fontSize: "0.7rem" },
  "& .MuiInputLabel-root": { fontSize: "0.75rem" },
} as const;

const SENSOR_RIG_CREATE_FIELDS = [
  { key: "name" as const, label: "Name", type: "text" as const, adornment: null },
  { key: "camera_model" as const, label: "Camera", type: "text" as const, adornment: null },
  {
    key: "stereo_baseline_m" as const,
    label: "Baseline",
    type: "number" as const,
    adornment: "m",
  },
  { key: "intrinsics_url" as const, label: "Intrinsics", type: "text" as const, adornment: null },
  { key: "extrinsics_url" as const, label: "Extrinsics", type: "text" as const, adornment: null },
  { key: "firmware_version" as const, label: "Firmware", type: "text" as const, adornment: null },
  { key: "isaac_ros_version" as const, label: "Isaac ROS", type: "text" as const, adornment: null },
] as const;

const toMessage = (error: unknown): string =>
  error instanceof Error ? error.message : "Request failed";

const getWarehouseStartPreflight = (error: unknown): PreflightRunResponse | null => {
  const body = (error as { body?: unknown } | null)?.body as WarehouseStartErrorBody | undefined;
  return body?.detail?.preflight ?? null;
};

const getWarehouseStartMessage = (error: unknown): string => {
  const body = (error as { body?: unknown } | null)?.body as WarehouseStartErrorBody | undefined;
  const detail = body?.detail ?? body?.error?.details;
  if (detail?.message) {
    const parts = [detail.message];
    const missing = [
      ...(detail.missing_required_topics ?? []),
      ...(detail.missing_nvblox_topics ?? []),
    ];
    if (missing.length > 0) {
      parts.push(`Missing: ${missing.join(", ")}`);
    }
    const actions = detail.suggested_actions ?? [];
    if (actions.length > 0) {
      parts.push(actions[0]);
    }
    return parts.join(" — ");
  }
  if (body?.error?.message) {
    return body.error.message;
  }
  if (error instanceof ApiError && error.detail) {
    return error.detail;
  }
  return toMessage(error);
};

const formatTimestamp = (value?: string | null): string => {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

type WarehouseMissionDefaultsKey = keyof WarehouseMissionDefaultsResponse;

type WarehouseMissionDefaultsDraft = {
  [K in WarehouseMissionDefaultsKey]: string;
};

type WarehouseMissionDefaultsRow =
  | {
      key: WarehouseMissionDefaultsKey;
      label: string;
      kind: "number";
      min?: number;
      step?: number;
      placeholder?: string;
    }
  | {
      key: WarehouseMissionDefaultsKey;
      label: string;
      kind: "select";
      options: ReadonlyArray<{ value: string; label: string }>;
    };

const WAREHOUSE_MISSION_DEFAULT_ROWS: WarehouseMissionDefaultsRow[] = [
  { key: "cruise_alt", label: "Base Layer Altitude (m)", kind: "number", min: 0.1, step: 0.1 },
  { key: "corridor_spacing_m", label: "Corridor Spacing (m)", kind: "number", min: 0.1, step: 0.1 },
  {
    key: "aisle_axis_deg",
    label: "Aisle Axis (deg)",
    kind: "number",
    min: -180,
    step: 1,
    placeholder: "Auto",
  },
  { key: "clearance_m", label: "Clearance (m)", kind: "number", min: 0.1, step: 0.1 },
  { key: "perimeter_offset_m", label: "Perimeter Offset (m)", kind: "number", min: 0, step: 0.1 },
  {
    key: "scan_pattern",
    label: "Scan Pattern",
    kind: "select",
    options: [
      { value: "aisle_serpentine", label: "Aisle Serpentine" },
      { value: "stacked_passes", label: "Stacked Passes" },
      { value: "crosshatch", label: "Crosshatch" },
      { value: "perimeter_aisle_hybrid", label: "Perimeter + Aisles" },
    ],
  },
  {
    key: "lane_strategy",
    label: "Lane Strategy",
    kind: "select",
    options: [
      { value: "serpentine", label: "Serpentine" },
      { value: "one_way", label: "One Way" },
    ],
  },
  {
    key: "view_mode",
    label: "View Mode",
    kind: "select",
    options: [
      { value: "forward", label: "Forward" },
      { value: "left_face", label: "Left Face" },
      { value: "right_face", label: "Right Face" },
      { value: "dual_face", label: "Dual Face" },
    ],
  },
  { key: "layer_count", label: "Layer Count", kind: "number", min: 1, step: 1 },
  { key: "layer_spacing_m", label: "Layer Spacing (m)", kind: "number", min: 0, step: 0.1 },
  { key: "ceiling_height_m", label: "Ceiling Height (m)", kind: "number", min: 0.1, step: 0.1 },
  { key: "ceiling_margin_m", label: "Ceiling Margin (m)", kind: "number", min: 0, step: 0.1 },
  { key: "work_speed_mps", label: "Work Speed (m/s)", kind: "number", min: 0.1, step: 0.1 },
  {
    key: "transit_speed_mps",
    label: "Transit Speed (m/s)",
    kind: "number",
    min: 0.1,
    step: 0.1,
  },
  { key: "scan_pause_s", label: "Scan Pause (s)", kind: "number", min: 0, step: 0.1 },
  {
    key: "interpolate_steps_work_leg",
    label: "Work Leg Interpolation",
    kind: "number",
    min: 0,
    step: 1,
  },
  {
    key: "interpolate_steps_transit_leg",
    label: "Transit Leg Interpolation",
    kind: "number",
    min: 0,
    step: 1,
  },
];

const WAREHOUSE_MISSION_DEFAULT_COLUMN_ROWS = (() => {
  const columnCount = 4;
  const rowsPerColumn = Math.ceil(WAREHOUSE_MISSION_DEFAULT_ROWS.length / columnCount);
  return Array.from({ length: columnCount }, (_, index) =>
    WAREHOUSE_MISSION_DEFAULT_ROWS.slice(
      index * rowsPerColumn,
      (index + 1) * rowsPerColumn,
    ),
  ).filter((column) => column.length > 0);
})();

const MISSION_DEFAULT_VALUE_SX = {
  ...COMPACT_FIELD_SX,
  width: "100%",
  maxWidth: 96,
  ml: "auto",
  "& .MuiInputBase-root": { fontSize: "0.68rem" },
  "& .MuiInputBase-input": {
    px: 0.5,
    py: 0.45,
    fontSize: "0.68rem",
    lineHeight: 1.2,
  },
  "& .MuiSelect-select": {
    fontSize: "0.68rem",
    py: 0.45,
    minHeight: "1.25rem",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
} as const;

const toWarehouseMissionDefaultsDraft = (
  defaults: WarehouseMissionDefaultsResponse,
): WarehouseMissionDefaultsDraft => ({
  cruise_alt: String(defaults.cruise_alt),
  corridor_spacing_m: String(defaults.corridor_spacing_m),
  aisle_axis_deg: defaults.aisle_axis_deg == null ? "" : String(defaults.aisle_axis_deg),
  clearance_m: String(defaults.clearance_m),
  perimeter_offset_m: String(defaults.perimeter_offset_m),
  scan_pattern: defaults.scan_pattern,
  lane_strategy: defaults.lane_strategy,
  view_mode: defaults.view_mode,
  layer_count: String(defaults.layer_count),
  layer_spacing_m: String(defaults.layer_spacing_m),
  ceiling_height_m: String(defaults.ceiling_height_m),
  ceiling_margin_m: String(defaults.ceiling_margin_m),
  work_speed_mps: String(defaults.work_speed_mps),
  transit_speed_mps: String(defaults.transit_speed_mps),
  scan_pause_s: String(defaults.scan_pause_s),
  interpolate_steps_work_leg: String(defaults.interpolate_steps_work_leg),
  interpolate_steps_transit_leg: String(defaults.interpolate_steps_transit_leg),
});

const parseRequiredNumber = (
  label: string,
  raw: string,
  integer = false,
): number => {
  const trimmed = raw.trim();
  if (!trimmed) {
    throw new Error(`${label} is required.`);
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be a valid number.`);
  }
  if (integer && !Number.isInteger(parsed)) {
    throw new Error(`${label} must be a whole number.`);
  }
  return parsed;
};

const parseOptionalNumber = (label: string, raw: string): number | null => {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const parsed = Number.parseFloat(trimmed);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be a valid number.`);
  }
  return parsed;
};

const toWarehouseMissionDefaultsPayload = (
  draft: WarehouseMissionDefaultsDraft,
): WarehouseMissionDefaultsResponse => ({
  cruise_alt: parseRequiredNumber("Cruise altitude", draft.cruise_alt),
  corridor_spacing_m: parseRequiredNumber("Corridor spacing", draft.corridor_spacing_m),
  aisle_axis_deg: parseOptionalNumber("Aisle axis", draft.aisle_axis_deg),
  clearance_m: parseRequiredNumber("Clearance", draft.clearance_m),
  perimeter_offset_m: parseRequiredNumber("Perimeter offset", draft.perimeter_offset_m),
  scan_pattern: draft.scan_pattern as WarehouseMissionDefaultsResponse["scan_pattern"],
  lane_strategy: draft.lane_strategy as WarehouseMissionDefaultsResponse["lane_strategy"],
  view_mode: draft.view_mode as WarehouseMissionDefaultsResponse["view_mode"],
  layer_count: parseRequiredNumber("Layer count", draft.layer_count, true),
  layer_spacing_m: parseRequiredNumber("Layer spacing", draft.layer_spacing_m),
  ceiling_height_m: parseRequiredNumber("Ceiling height", draft.ceiling_height_m),
  ceiling_margin_m: parseRequiredNumber("Ceiling margin", draft.ceiling_margin_m),
  work_speed_mps: parseRequiredNumber("Work speed", draft.work_speed_mps),
  transit_speed_mps: parseRequiredNumber("Transit speed", draft.transit_speed_mps),
  scan_pause_s: parseRequiredNumber("Scan pause", draft.scan_pause_s),
  interpolate_steps_work_leg: parseRequiredNumber(
    "Work leg interpolation",
    draft.interpolate_steps_work_leg,
    true,
  ),
  interpolate_steps_transit_leg: parseRequiredNumber(
    "Transit leg interpolation",
    draft.interpolate_steps_transit_leg,
    true,
  ),
});


export default function WarehousePage() {
  const warehouseSetupDrawer = useTaskPreflightCommandsDrawer();
  const warehouseMissionDrawer = useTaskPreflightCommandsDrawer();
  const warehousePreflightDrawer = useTaskPreflightCommandsDrawer();

  const closeOtherWarehouseDrawers = useCallback(
    (except: "setup" | "mission" | "preflight") => {
      if (except !== "setup") warehouseSetupDrawer.closeDrawer();
      if (except !== "mission") warehouseMissionDrawer.closeDrawer();
      if (except !== "preflight") warehousePreflightDrawer.closeDrawer();
    },
    [warehouseMissionDrawer, warehousePreflightDrawer, warehouseSetupDrawer],
  );

  const handleWarehouseSetupOpenChange = useCallback(
    (open: boolean) => {
      warehouseSetupDrawer.onOpenChange(open);
      if (open) closeOtherWarehouseDrawers("setup");
    },
    [closeOtherWarehouseDrawers, warehouseSetupDrawer],
  );

  const handleWarehouseMissionOpenChange = useCallback(
    (open: boolean) => {
      warehouseMissionDrawer.onOpenChange(open);
      if (open) closeOtherWarehouseDrawers("mission");
    },
    [closeOtherWarehouseDrawers, warehouseMissionDrawer],
  );

  const handleWarehousePreflightOpenChange = useCallback(
    (open: boolean) => {
      warehousePreflightDrawer.onOpenChange(open);
      if (open) closeOtherWarehouseDrawers("preflight");
    },
    [closeOtherWarehouseDrawers, warehousePreflightDrawer],
  );
  const [scannedMaps, setScannedMaps] = useState<WarehouseScannedMapResponse[]>([]);
  const [loadingScannedMaps, setLoadingScannedMaps] = useState(false);
  const [deletingScannedMap, setDeletingScannedMap] = useState(false);
  const [selectedMapJobId, setSelectedMapJobId] = useState<number | null>(null);
  const [viewerMapJobId, setViewerMapJobId] = useState<number | null>(null);
  const [selectedReferenceJobId, setSelectedReferenceJobId] = useState<number | null>(null);

  // Warehouse maps (footprints) — separate from scanned results
  const [warehouseMaps, setWarehouseMaps] = useState<WarehouseMapOut[]>([]);
  const [loadingWarehouseMaps, setLoadingWarehouseMaps] = useState(false);
  const [selectedWarehouseMapId, setSelectedWarehouseMapId] = useState<number | null>(null);
  const [selectedDockId, setSelectedDockId] = useState<number | null>(null);
  const [createMapForm, setCreateMapForm] = useState<CreateMapForm>({ name: "", width_m: "", length_m: "" });
  const [creatingMap, setCreatingMap] = useState(false);
  const [deletingWarehouseMap, setDeletingWarehouseMap] = useState(false);
  const [showCreateMap, setShowCreateMap] = useState(false);
  const [sensorRigs, setSensorRigs] = useState<WarehouseSensorRig[]>([]);
  const [selectedSensorRigId, setSelectedSensorRigId] = useState<number | null>(null);
  const [sensorRigHealth, setSensorRigHealth] = useState<WarehouseSensorRigHealth | null>(null);
  const [warehousePreflightRun, setWarehousePreflightRun] =
    useState<PreflightRunResponse | null>(null);
  const [loadingSensorRigs, setLoadingSensorRigs] = useState(false);
  const [savingSensorRig, setSavingSensorRig] = useState(false);
  const [deletingSensorRig, setDeletingSensorRig] = useState(false);
  const [showCreateSensorRig, setShowCreateSensorRig] = useState(false);
  const [sensorRigForm, setSensorRigForm] = useState<SensorRigForm>({
    name: "",
    camera_model: "",
    stereo_baseline_m: "",
    intrinsics_url: "",
    extrinsics_url: "",
    firmware_version: "",
    isaac_ros_version: "",
  });
  const [missionDefaultsDraft, setMissionDefaultsDraft] =
    useState<WarehouseMissionDefaultsDraft | null>(null);
  const [loadingMissionDefaults, setLoadingMissionDefaults] = useState(false);
  const [savingMissionDefaults, setSavingMissionDefaults] = useState(false);
  const [missionDefaultsMessage, setMissionDefaultsMessage] = useState<string | null>(null);

  const [startingScan, setStartingScan] = useState(false);
  const [scanLaunchMessage, setScanLaunchMessage] = useState<string | null>(null);

  const [manualStreamKey, setManualStreamKey] = useState<{
    flightId: string | null;
    key: number;
  } | null>(null);
  const [videoErrorMessage, setVideoErrorMessage] = useState<string | null>(null);
  const [videoErrorStreamKey, setVideoErrorStreamKey] = useState<number | null>(null);
  const [videoRetryCount, setVideoRetryCount] = useState(0);

  const retryTimerRef = useRef<number | null>(null);
  const viewerSectionRef = useRef<HTMLDivElement | null>(null);
  const previousMissionStateRef = useRef<MissionLifecycleState | null>(null);
  const { errors, addError, clearErrors, dismissError } = useErrors();

  const apiBaseRaw = import.meta.env.VITE_API_BASE_URL ?? "";
  const apiBase = (apiBaseRaw || "http://localhost:8000").replace(/\/$/, "");
  const videoToken = getToken();

  const {
    missionStatus,
    activeFlightId,
    setPendingFlightId,
    telemetry,
    wsConnected,
    disconnect,
    droneConnected,
  } = useMissionWebsocketRuntime<WarehouseMissionStatus>({
    apiBase,
    getTokenFn: getToken,
    onError: addError,
    alwaysConnect: true,
  });

  const { startingVideo, streamKey: autoStreamKey } = useAutoStartVideo({
    apiBase,
    getToken,
    enabled: Boolean(activeFlightId && droneConnected),
    onError: addError,
    resetKey: activeFlightId ?? "none",
  });

  const selectedScannedMap = useMemo(
    () => selectScannedMap(scannedMaps, selectedMapJobId),
    [scannedMaps, selectedMapJobId],
  );

  const viewerScannedMap = useMemo(
    () => selectScannedMap(scannedMaps, viewerMapJobId),
    [scannedMaps, viewerMapJobId],
  );

  const loadScannedMaps = useCallback(
    async (options?: { selectJobId?: number; showInViewer?: boolean }) => {
    const token = getToken();
    if (!token) return [];

    setLoadingScannedMaps(true);
    try {
      const records = await listWarehouseScannedMaps(token);
      setScannedMaps(records);

      const explicitJobId = options?.selectJobId;
      if (explicitJobId != null) {
        setSelectedMapJobId(explicitJobId);
        if (options?.showInViewer) {
          setViewerMapJobId(explicitJobId);
        }
      } else {
        setSelectedMapJobId((current) => {
          if (current != null && records.some((record) => record.job_id === current)) {
            return current;
          }
          return records[0]?.job_id ?? null;
        });
      }
      return records;
    } catch (error) {
      addError(`Scanned warehouse maps could not be loaded: ${toMessage(error)}`);
      return [];
    } finally {
      setLoadingScannedMaps(false);
    }
  },
    [addError],
  );

  const showSelectedScanInViewer = useCallback(() => {
    if (!selectedScannedMap) return;
    setViewerMapJobId(selectedScannedMap.job_id);
    viewerSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [selectedScannedMap]);

  const handleScanResultReady = useCallback(
    (jobId: number) => {
      void loadScannedMaps({ selectJobId: jobId, showInViewer: true }).then(() => {
        viewerSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      setScanLaunchMessage(`Scan result #${jobId} saved to Previous Scan Results.`);
    },
    [loadScannedMaps],
  );

  const handleDeleteScannedMap = useCallback(async () => {
    if (!selectedScannedMap) return;
    const token = getToken();
    if (!token) {
      addError("You must be authenticated to delete scan results.");
      return;
    }
    const jobId = selectedScannedMap.job_id;
    const label = `${getWarehouseName(selectedScannedMap)} • job #${jobId}`;
    if (!window.confirm(`Delete scan result "${label}"? This cannot be undone.`)) {
      return;
    }

    setDeletingScannedMap(true);
    try {
      await deleteWarehouseScannedMap(jobId, token);
      if (viewerMapJobId === jobId) {
        setViewerMapJobId(null);
      }
      if (selectedReferenceJobId === jobId) {
        setSelectedReferenceJobId(null);
      }
      setSelectedMapJobId(null);
      await loadScannedMaps();
      setScanLaunchMessage(`Deleted scan result #${jobId}.`);
    } catch (error) {
      addError(`Could not delete scan result: ${toMessage(error)}`);
    } finally {
      setDeletingScannedMap(false);
    }
  }, [
    addError,
    loadScannedMaps,
    selectedReferenceJobId,
    selectedScannedMap,
    viewerMapJobId,
  ]);

  const loadMissionDefaults = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    setLoadingMissionDefaults(true);
    try {
      const defaults = await fetchWarehouseMissionDefaults(token);
      setMissionDefaultsDraft(toWarehouseMissionDefaultsDraft(defaults));
    } catch (error) {
      addError(`Warehouse mission defaults could not be loaded: ${toMessage(error)}`);
    } finally {
      setLoadingMissionDefaults(false);
    }
  }, [addError]);

  const loadWarehouseMaps = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoadingWarehouseMaps(true);
    try {
      const maps = await listWarehouseMaps(token);
      setWarehouseMaps(maps);
      // Auto-select the first map if nothing is selected yet
      setSelectedWarehouseMapId((current) => {
        if (current != null && maps.some((m) => m.id === current)) return current;
        return maps[0]?.id ?? null;
      });
    } catch (error) {
      addError(`Warehouse maps could not be loaded: ${toMessage(error)}`);
    } finally {
      setLoadingWarehouseMaps(false);
    }
  }, [addError]);

  const loadSensorRigs = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoadingSensorRigs(true);
    try {
      const rigs = await listWarehouseSensorRigs(token);
      setSensorRigs(rigs);
      setSelectedSensorRigId((current) => {
        if (current != null && rigs.some((rig) => rig.id === current)) return current;
        return rigs[0]?.id ?? null;
      });
    } catch (error) {
      addError(`Sensor rigs could not be loaded: ${toMessage(error)}`);
    } finally {
      setLoadingSensorRigs(false);
    }
  }, [addError]);

  const loadSensorRigHealth = useCallback(
    async (sensorRigId: number | null) => {
      const token = getToken();
      if (!token || sensorRigId == null) {
        setSensorRigHealth(null);
        return;
      }
      try {
        const health = await fetchWarehouseSensorRigHealth(sensorRigId, token);
        setSensorRigHealth(health);
      } catch (error) {
        setSensorRigHealth(null);
        addError(`Sensor rig health could not be loaded: ${toMessage(error)}`);
      }
    },
    [addError],
  );

  const handleCreateWarehouseMap = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    const name = createMapForm.name.trim();
    if (!name) { addError("Map name is required."); return; }
    const width = Number(createMapForm.width_m);
    const length = Number(createMapForm.length_m);
    if (!Number.isFinite(width) || width <= 0) { addError("Width must be a positive number."); return; }
    if (!Number.isFinite(length) || length <= 0) { addError("Length must be a positive number."); return; }
    setCreatingMap(true);
    try {
      const created = await createWarehouseMap(
        { name, width_m: width, length_m: length },
        token,
      );
      setCreateMapForm({ name: "", width_m: "", length_m: "" });
      setShowCreateMap(false);
      await loadWarehouseMaps();
      setSelectedWarehouseMapId(created.id);
      setScanLaunchMessage(`Warehouse map "${created.name}" saved.`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        addError(
          "Could not create warehouse map: insufficient permissions. Check your account role in the sidebar (needs operator/pilot or higher). Restart the backend if this persists after a recent update.",
        );
      } else {
        addError(`Could not create warehouse map: ${toMessage(error)}`);
      }
    } finally {
      setCreatingMap(false);
    }
  }, [addError, createMapForm, loadWarehouseMaps]);

  const handleDeleteWarehouseMap = useCallback(async () => {
    if (selectedWarehouseMapId == null) return;
    const token = getToken();
    if (!token) {
      addError("You must be authenticated to delete warehouse maps.");
      return;
    }
    const map = warehouseMaps.find((item) => item.id === selectedWarehouseMapId);
    const label = map?.name ?? `Map #${selectedWarehouseMapId}`;
    if (!window.confirm(`Delete warehouse map "${label}"? This cannot be undone.`)) {
      return;
    }

    setDeletingWarehouseMap(true);
    try {
      await deleteWarehouseMap(selectedWarehouseMapId, token);
      if (selectedWarehouseMapId != null) {
        setSelectedDockId(null);
      }
      setSelectedWarehouseMapId(null);
      await loadWarehouseMaps();
      setScanLaunchMessage(`Deleted warehouse map "${label}".`);
    } catch (error) {
      addError(`Could not delete warehouse map: ${toMessage(error)}`);
    } finally {
      setDeletingWarehouseMap(false);
    }
  }, [addError, loadWarehouseMaps, selectedWarehouseMapId, warehouseMaps]);

  const handleCreateSensorRig = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    const name = sensorRigForm.name.trim();
    const cameraModel = sensorRigForm.camera_model.trim();
    if (!name) {
      addError("Sensor rig name is required.");
      return;
    }
    if (!cameraModel) {
      addError("Camera model is required.");
      return;
    }
    const baselineRaw = sensorRigForm.stereo_baseline_m.trim();
    const baseline = baselineRaw ? Number(baselineRaw) : null;
    if (baselineRaw && (!Number.isFinite(baseline) || Number(baseline) <= 0)) {
      addError("Stereo baseline must be a positive number.");
      return;
    }
    setSavingSensorRig(true);
    try {
      const created = await createWarehouseSensorRig(
        {
          name,
          camera_model: cameraModel,
          stereo_baseline_m: baseline,
          intrinsics_url: sensorRigForm.intrinsics_url.trim() || null,
          extrinsics_url: sensorRigForm.extrinsics_url.trim() || null,
          firmware_version: sensorRigForm.firmware_version.trim() || null,
          isaac_ros_version: sensorRigForm.isaac_ros_version.trim() || null,
          imu_transform_json: {},
        },
        token,
      );
      setSensorRigForm({
        name: "",
        camera_model: "",
        stereo_baseline_m: "",
        intrinsics_url: "",
        extrinsics_url: "",
        firmware_version: "",
        isaac_ros_version: "",
      });
      setShowCreateSensorRig(false);
      await loadSensorRigs();
      setSelectedSensorRigId(created.id);
      if (created.calibration_status !== "valid") {
        await updateWarehouseSensorRigCalibration(
          created.id,
          {
            calibration_status: "valid",
            calibration_hash: created.calibration_hash ?? `manual-${Date.now()}`,
            intrinsics_url: created.intrinsics_url,
            extrinsics_url: created.extrinsics_url,
            imu_transform_json: created.imu_transform_json,
            calibration_meta: {
              ...created.calibration_meta,
              source: "operator_create",
              updated_at: new Date().toISOString(),
            },
          },
          token,
        );
        await loadSensorRigs();
      }
      await loadSensorRigHealth(created.id);
    } catch (error) {
      addError(`Could not create sensor rig: ${toMessage(error)}`);
    } finally {
      setSavingSensorRig(false);
    }
  }, [addError, loadSensorRigHealth, loadSensorRigs, sensorRigForm]);

  const handleDeleteSensorRig = useCallback(async () => {
    if (selectedSensorRigId == null) return;
    const token = getToken();
    if (!token) {
      addError("You must be authenticated to delete sensor rigs.");
      return;
    }
    const rig = sensorRigs.find((item) => item.id === selectedSensorRigId);
    const label = rig?.name ?? `Sensor rig #${selectedSensorRigId}`;
    if (!window.confirm(`Delete sensor rig "${label}"? This cannot be undone.`)) {
      return;
    }

    setDeletingSensorRig(true);
    try {
      await deleteWarehouseSensorRig(selectedSensorRigId, token);
      setSelectedSensorRigId(null);
      setSensorRigHealth(null);
      await loadSensorRigs();
      setScanLaunchMessage(`Deleted sensor rig "${label}".`);
    } catch (error) {
      addError(`Could not delete sensor rig: ${toMessage(error)}`);
    } finally {
      setDeletingSensorRig(false);
    }
  }, [addError, loadSensorRigs, selectedSensorRigId, sensorRigs]);

  const handleMarkSensorRigCalibrated = useCallback(async () => {
    const token = getToken();
    if (!token || selectedSensorRigId == null) return;
    const rig = sensorRigs.find((item) => item.id === selectedSensorRigId);
    if (!rig) return;
    setSavingSensorRig(true);
    try {
      await updateWarehouseSensorRigCalibration(
        selectedSensorRigId,
        {
          calibration_status: "valid",
          calibration_hash: rig.calibration_hash ?? `manual-${Date.now()}`,
          intrinsics_url: rig.intrinsics_url,
          extrinsics_url: rig.extrinsics_url,
          imu_transform_json: rig.imu_transform_json,
          calibration_meta: {
            ...rig.calibration_meta,
            source: "operator_update",
            updated_at: new Date().toISOString(),
          },
        },
        token,
      );
      await loadSensorRigs();
      await loadSensorRigHealth(selectedSensorRigId);
    } catch (error) {
      addError(`Could not update sensor rig calibration: ${toMessage(error)}`);
    } finally {
      setSavingSensorRig(false);
    }
  }, [addError, loadSensorRigHealth, loadSensorRigs, selectedSensorRigId, sensorRigs]);

  useEffect(() => {
    return () => {
      if (retryTimerRef.current !== null) {
        window.clearTimeout(retryTimerRef.current);
      }
      disconnect();
    };
  }, [disconnect]);

  useEffect(() => {
    void loadScannedMaps();
  }, [loadScannedMaps]);

  useEffect(() => {
    void loadMissionDefaults();
  }, [loadMissionDefaults]);

  useEffect(() => {
    void loadWarehouseMaps();
  }, [loadWarehouseMaps]);

  useEffect(() => {
    void loadSensorRigs();
  }, [loadSensorRigs]);

  useEffect(() => {
    void loadSensorRigHealth(selectedSensorRigId);
  }, [loadSensorRigHealth, selectedSensorRigId]);

  useEffect(() => {
    const handle = window.setInterval(() => {
      void loadScannedMaps();
    }, SCANNED_MAP_REFRESH_MS);
    return () => window.clearInterval(handle);
  }, [loadScannedMaps]);

  useEffect(() => {
    const state = missionStatus?.mission_lifecycle?.state ?? null;
    const previous = previousMissionStateRef.current;
    if (
      (previous === "running" || previous === "paused") &&
      (state === "completed" || state === "failed" || state === "aborted")
    ) {
      void loadScannedMaps().then((records) => {
        const scoped =
          selectedWarehouseMapId != null
            ? records.filter((record) => getWarehouseMapId(record) === selectedWarehouseMapId)
            : records;
        const newest = scoped[0];
        if (newest) {
          setSelectedMapJobId(newest.job_id);
        }
      });
    }
    previousMissionStateRef.current = state;
  }, [loadScannedMaps, missionStatus?.mission_lifecycle?.state, selectedWarehouseMapId]);

  const streamKey =
    manualStreamKey?.flightId === (activeFlightId ?? null)
      ? manualStreamKey.key
      : autoStreamKey;

  const videoError =
    videoErrorStreamKey !== null && videoErrorStreamKey === streamKey
      ? videoErrorMessage
      : null;

  const handleVideoError = useCallback(() => {
    setVideoErrorMessage("Failed to load video stream");
    setVideoErrorStreamKey(streamKey || null);
    setVideoRetryCount((prev) => prev + 1);

    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
    }

    retryTimerRef.current = window.setTimeout(() => {
      setManualStreamKey({
        flightId: activeFlightId ?? null,
        key: Date.now(),
      });
      setVideoErrorMessage(null);
      setVideoErrorStreamKey(null);
      retryTimerRef.current = null;
    }, VIDEO_RETRY_DELAY_MS);
  }, [activeFlightId, streamKey]);

  const handleVideoLoad = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    setVideoErrorMessage(null);
    setVideoErrorStreamKey(null);
    setVideoRetryCount(0);
  }, []);

  const handleStartWarehouseScan = useCallback(async () => {
    const token = getToken();
    if (!token) {
      addError("You must be authenticated to start a warehouse scan.");
      return;
    }
    if (!selectedWarehouseMapId) {
      addError("Select a warehouse map to define the scan area.");
      return;
    }
    if (selectedSensorRigId == null || sensorRigHealth?.ready !== true) {
      addError("Select a calibrated warehouse sensor rig before starting the scan.");
      return;
    }

    const warehouseMap = warehouseMaps.find((m) => m.id === selectedWarehouseMapId);

    setStartingScan(true);
    setScanLaunchMessage(null);
    setWarehousePreflightRun(null);
    try {
      const launch = await startWarehouseScan(
        {
          warehouse_map_id: selectedWarehouseMapId,
          mission_name: `Warehouse Scan${warehouseMap ? ` - ${warehouseMap.name}` : ""}`,
          sensor_rig_id: selectedSensorRigId,
          dock_id: selectedDockId,
          // Link to the most recent scanned result for this map as reference, if available
          reference_mapping_job_id:
            selectedReferenceJobId ??
            scannedMaps.find((m) => getWarehouseMapId(m) === selectedWarehouseMapId)?.job_id,
        },
        token,
      );

      setPendingFlightId(launch.mission.flight_id);
      setWarehousePreflightRun(launch.preflight);
      const launchWarehouseName = launch.warehouse_name.trim() || "Warehouse";
      setScanLaunchMessage(
        `Started ${launch.mission.mission_name} in ${launchWarehouseName}. Preflight ${launch.preflight.overall_status}.`,
      );
      void loadScannedMaps();
    } catch (error) {
      const preflight = getWarehouseStartPreflight(error);
      if (preflight) {
        setWarehousePreflightRun(preflight);
      }
      addError(`Warehouse scan could not be started: ${getWarehouseStartMessage(error)}`);
    } finally {
      setStartingScan(false);
    }
  }, [
    addError,
    loadScannedMaps,
    scannedMaps,
    selectedDockId,
    selectedReferenceJobId,
    selectedSensorRigId,
    selectedWarehouseMapId,
    sensorRigHealth?.ready,
    warehouseMaps,
    setPendingFlightId,
  ]);

  const handleExplorationLaunch = useCallback(
    (launch: WarehouseMissionLaunchResponse) => {
      setPendingFlightId(launch.mission.flight_id);
      setWarehousePreflightRun(launch.preflight);
      const launchWarehouseName = launch.warehouse_name.trim() || "Warehouse";
      setScanLaunchMessage(
        `Started ${launch.mission.mission_name} in ${launchWarehouseName}. Preflight ${launch.preflight.overall_status}.`,
      );
    },
    [setPendingFlightId],
  );

  const handleExplorationError = useCallback(
    (message: string, error?: unknown) => {
      const preflight = getWarehouseStartPreflight(error);
      if (preflight) setWarehousePreflightRun(preflight);
      addError(`${message}${error ? ` ${toMessage(error)}` : ""}`);
    },
    [addError],
  );

  const handleMissionDefaultsDraftChange = useCallback(
    (key: WarehouseMissionDefaultsKey, value: string) => {
      setMissionDefaultsDraft((current) =>
        current
          ? {
              ...current,
              [key]: value,
            }
          : current,
      );
      setMissionDefaultsMessage(null);
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
    setMissionDefaultsMessage(null);
    try {
      const saved = await updateWarehouseMissionDefaults(payload, token);
      setMissionDefaultsDraft(toWarehouseMissionDefaultsDraft(saved));
      setMissionDefaultsMessage("Warehouse mission defaults updated.");
    } catch (error) {
      addError(`Warehouse mission defaults could not be updated: ${toMessage(error)}`);
    } finally {
      setSavingMissionDefaults(false);
    }
  }, [addError, missionDefaultsDraft]);

  const missionName =
    missionStatus?.mission_lifecycle?.mission_name ??
    missionStatus?.mission_name ??
    "No active warehouse mission";
  const missionState = missionStatus?.mission_lifecycle?.state ?? "idle";
  const startScanDisabled =
    startingScan ||
    !selectedWarehouseMapId ||
    selectedSensorRigId == null ||
    sensorRigHealth?.ready !== true;
  const startScanTooltip = !selectedWarehouseMapId
    ? "Select a warehouse map to enable launch."
    : selectedSensorRigId == null || sensorRigHealth?.ready !== true
      ? "Select a registered sensor rig before starting."
      : !sensorRigHealth?.perception?.ready
        ? "Launch scan — mapping stack and perception start with the flight."
        : `Scan warehouse map #${selectedWarehouseMapId}.`;

  const selectedWarehouseMapName = useMemo(() => {
    if (selectedWarehouseMapId == null) return null;
    return warehouseMaps.find((map) => map.id === selectedWarehouseMapId)?.name ?? null;
  }, [selectedWarehouseMapId, warehouseMaps]);

  return (
    <>
      <Header />
      <Paper
        sx={{
          width: "100%",
          p: 3,
          borderRadius: 1,
          backgroundColor: "background.paper",
          border: "1px solid",
          borderColor: "divider",
        }}
      >
        <Stack
          direction={{ xs: "column", md: "row" }}
          alignItems={{ xs: "flex-start", md: "center" }}
          justifyContent="space-between"
          sx={{ mb: 2 }}
          spacing={1}
        >
          <Box>
            <Typography variant="h5">
              <InfoLabel
                label="Warehouse Operations"
                info="Launch warehouse scans, monitor mission state, stream the live camera, and review recorded 3D warehouse maps."
              />
            </Typography>
          </Box>
          <MissionStatusChips
            droneConnected={droneConnected}
            wsConnected={wsConnected}
          />
        </Stack>

        <ErrorAlerts
          errors={errors}
          onDismiss={dismissError}
          onClearAll={clearErrors}
        />

        {scanLaunchMessage && (
          <Alert severity="success" sx={{ mb: 3 }}>
            {scanLaunchMessage}
          </Alert>
        )}

        <Stack sx={{ minWidth: 0 }} spacing={2}>

            <MissionVideoPanel
                title="Warehouse Camera"
                imgAlt="Warehouse camera stream"
                disconnectedMessage="Connect the drone to view the warehouse stream."
                apiBase={apiBase}
                streamKey={streamKey}
                videoToken={videoToken}
                startingVideo={startingVideo}
                videoError={videoError}
                videoRetryCount={videoRetryCount}
                droneConnected={droneConnected}
                telemetry={telemetry}
                onVideoError={handleVideoError}
                onVideoLoad={handleVideoLoad}
                onRetry={() => {
                  setManualStreamKey({
                    flightId: activeFlightId ?? null,
                    key: Date.now(),
                  });
                  setVideoErrorMessage(null);
                  setVideoErrorStreamKey(null);
                }}
            />

            <WarehouseMappingHealthPanel status={missionStatus?.warehouse_mapping ?? null} />

            <Stack spacing={1} ref={viewerSectionRef} id="warehouse-3d-map-viewer">
              <Paper
                variant="outlined"
                sx={{
                  p: 2,
                  borderRadius: 1,
                  borderColor: "divider",
                  backgroundColor: "background.paper",
                }}
              >
                <WarehouseScanViewer
                  apiBase={apiBase}
                  getToken={getToken}
                  map={viewerScannedMap}
                />
              </Paper>
            </Stack>

            <Paper
              variant="outlined"
              sx={{
                p: 2,
                borderRadius: 2,
                borderColor: "divider",
                backgroundColor: "background.paper",
              }}
            >
              <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
                Mission Status
              </Typography>

              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: {
                    xs: "1fr",
                    sm: "repeat(2, minmax(0, 1fr))",
                  },
                  gap: 1.5,
                }}
              >
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Mission
                  </Typography>
                  <Typography variant="body1">{missionName}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    State
                  </Typography>
                  <Typography variant="body1" sx={{ textTransform: "capitalize" }}>
                    {missionState.replace(/_/g, " ")}
                  </Typography>
                </Box>
                {activeFlightId && (
                  <Box sx={{ gridColumn: { sm: "1 / -1" } }}>
                    <Typography variant="caption" color="text.secondary">
                      Active Flight
                    </Typography>
                    <Typography variant="body1">{activeFlightId}</Typography>
                  </Box>
                )}
              </Box>

              {missionStatus?.mission_lifecycle?.last_error && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  {missionStatus.mission_lifecycle.last_error}
                </Alert>
              )}

              <Stack direction="row" justifyContent="flex-end" sx={{ mt: 2 }}>
                <ActionIconButton
                  variant="play"
                  title={
                    startScanDisabled
                      ? startScanTooltip
                      : startingScan
                        ? "Starting Flight & Scan…"
                        : "Start Flight & Scan"
                  }
                  color="primary"
                  size="large"
                  loading={startingScan}
                  disabled={startScanDisabled}
                  onClick={() => {
                    void handleStartWarehouseScan();
                  }}
                />
              </Stack>
            </Paper>
        </Stack>
      </Paper>

      <TaskPreflightCommandsDrawer
        open={warehouseSetupDrawer.open}
        onOpenChange={handleWarehouseSetupOpenChange}
        title="Warehouse Setup"
        subtitle="Map, sensor rig, dock, and scan defaults"
        tabLabel="SETUP"
        tabIcon={<TuneRoundedIcon fontSize="small" />}
        edgeTabIndex={0}
        edgeTabCount={3}
        paperSx={{ width: { xs: "min(100vw, 520px)", sm: 540, md: 560 } }}
      >
        <Stack spacing={2}>
          <WarehouseDrawerSection
            title="Warehouse Map"
            info="Select the warehouse footprint. The drone scans using local metric coordinates — no GPS required. Origin (0, 0) is the takeoff position."
            action={loadingWarehouseMaps ? <CircularProgress size={16} /> : null}
          >
            <Stack
              direction="row"
              spacing={0.75}
              alignItems="flex-start"
              useFlexGap
              sx={{ flexWrap: "wrap", minWidth: 0 }}
            >
              <TextField
                select
                size="small"
                label="Map"
                value={selectedWarehouseMapId != null ? String(selectedWarehouseMapId) : ""}
                onChange={(event) => {
                  const raw = event.target.value;
                  setSelectedWarehouseMapId(raw ? Number(raw) : null);
                  setSelectedDockId(null);
                }}
                disabled={loadingWarehouseMaps}
                helperText={
                  warehouseMaps.length === 0
                    ? "No maps yet"
                    : selectedWarehouseMapId
                      ? (() => {
                          const m = warehouseMaps.find((x) => x.id === selectedWarehouseMapId);
                          return m
                            ? `${m.area_m2 != null ? `${Math.round(m.area_m2)} m²` : "area unknown"}`
                            : `#${selectedWarehouseMapId}`;
                        })()
                      : undefined
                }
                sx={{ ...COMPACT_FIELD_SX, flex: "1 1 160px", minWidth: 140, maxWidth: 360 }}
              >
                {warehouseMaps.length === 0 && (
                  <MenuItem value="" disabled>
                    No warehouse maps registered
                  </MenuItem>
                )}
                {warehouseMaps.map((m) => (
                  <MenuItem key={m.id} value={String(m.id)}>
                    {`${m.name}${m.area_m2 != null ? ` • ${Math.round(m.area_m2)} m²` : ""}`}
                  </MenuItem>
                ))}
              </TextField>
              <Stack direction="row" spacing={0.25} alignItems="center" sx={{ flexShrink: 0, pt: 0.25 }}>
                <ActionIconButton
                  variant="refresh"
                  title="Refresh"
                  loading={loadingWarehouseMaps}
                  onClick={() => {
                    void loadWarehouseMaps();
                  }}
                />
                <ActionIconButton
                  variant="add"
                  title={showCreateMap ? "Cancel" : "New Map"}
                  color={showCreateMap ? "primary" : "default"}
                  onClick={() => setShowCreateMap((v) => !v)}
                />
                <ActionIconButton
                  variant="delete"
                  title={deletingWarehouseMap ? "Deleting…" : "Delete Map"}
                  color="error"
                  loading={deletingWarehouseMap}
                  disabled={selectedWarehouseMapId == null}
                  onClick={() => {
                    void handleDeleteWarehouseMap();
                  }}
                />
              </Stack>
              {showCreateMap && (
                <>
                  <TextField
                    size="small"
                    label="Name"
                    value={createMapForm.name}
                    onChange={(e) => setCreateMapForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="e.g. Aisle A–F"
                    sx={{ ...COMPACT_FIELD_SX, flex: "1 1 120px", minWidth: 100 }}
                  />
                  <TextField
                    size="small"
                    type="number"
                    label="Width"
                    inputProps={{ min: 0.1, step: 0.5 }}
                    InputProps={{
                      endAdornment: <InputAdornment position="end">m</InputAdornment>,
                    }}
                    value={createMapForm.width_m}
                    onChange={(e) => setCreateMapForm((f) => ({ ...f, width_m: e.target.value }))}
                    sx={{ ...COMPACT_FIELD_SX, flex: "0 1 88px", minWidth: 72 }}
                  />
                  <TextField
                    size="small"
                    type="number"
                    label="Length"
                    inputProps={{ min: 0.1, step: 0.5 }}
                    InputProps={{
                      endAdornment: <InputAdornment position="end">m</InputAdornment>,
                    }}
                    value={createMapForm.length_m}
                    onChange={(e) => setCreateMapForm((f) => ({ ...f, length_m: e.target.value }))}
                    sx={{ ...COMPACT_FIELD_SX, flex: "0 1 88px", minWidth: 72 }}
                  />
                  <ActionIconButton
                    variant="add"
                    title={creatingMap ? "Creating…" : "Create Map"}
                    color="primary"
                    loading={creatingMap}
                    onClick={() => {
                      void handleCreateWarehouseMap();
                    }}
                    sx={{ mt: 0.25, flexShrink: 0 }}
                  />
                </>
              )}
            </Stack>
          </WarehouseDrawerSection>

          <WarehouseDrawerSection
            title="Sensor Rig"
            info="Register calibrated stereo/RGB-D camera and IMU hardware for ROS 2 mapping."
            action={loadingSensorRigs ? <CircularProgress size={16} /> : null}
          >
            <Stack direction="row" spacing={0.75} alignItems="flex-start" sx={{ minWidth: 0 }}>
              <TextField
                select
                size="small"
                label="Camera + IMU Rig"
                value={selectedSensorRigId != null ? String(selectedSensorRigId) : ""}
                onChange={(event) => {
                  const raw = event.target.value;
                  setSelectedSensorRigId(raw ? Number(raw) : null);
                }}
                helperText={
                  sensorRigHealth
                    ? sensorRigHealth.ready
                      ? sensorRigHealth.perception?.ready
                        ? "Ready"
                        : sensorRigHealth.warnings?.[0] ??
                          "Registered — perception stack starts with flight"
                      : sensorRigHealth.blockers[0] ?? "Not ready"
                    : undefined
                }
                sx={{ ...COMPACT_FIELD_SX, flex: 1 }}
              >
                {sensorRigs.length === 0 && (
                  <MenuItem value="" disabled>
                    No sensor rigs registered
                  </MenuItem>
                )}
                {sensorRigs.map((rig) => (
                  <MenuItem key={rig.id} value={String(rig.id)}>
                    {`${rig.name} • ${rig.camera_model} • ${rig.calibration_status}`}
                  </MenuItem>
                ))}
              </TextField>
              <Stack direction="row" spacing={0.25} alignItems="center" sx={{ flexShrink: 0, pt: 0.25 }}>
                <ActionIconButton
                  variant="refresh"
                  title="Refresh"
                  loading={loadingSensorRigs}
                  onClick={() => {
                    void loadSensorRigs();
                    void loadSensorRigHealth(selectedSensorRigId);
                  }}
                />
                <ActionIconButton
                  variant="check"
                  title="Calibrated"
                  loading={savingSensorRig}
                  disabled={selectedSensorRigId == null}
                  onClick={() => {
                    void handleMarkSensorRigCalibrated();
                  }}
                />
                <ActionIconButton
                  variant="add"
                  title={showCreateSensorRig ? "Cancel" : "New Sensor Rig"}
                  color={showCreateSensorRig ? "primary" : "default"}
                  onClick={() => setShowCreateSensorRig((value) => !value)}
                />
                <ActionIconButton
                  variant="delete"
                  title={deletingSensorRig ? "Deleting…" : "Delete Sensor Rig"}
                  color="error"
                  loading={deletingSensorRig}
                  disabled={selectedSensorRigId == null}
                  onClick={() => {
                    void handleDeleteSensorRig();
                  }}
                />
              </Stack>
            </Stack>
            {showCreateSensorRig && (
              <Stack
                spacing={1}
                sx={{ mt: 1, p: 1.5, borderRadius: 1, border: "1px solid", borderColor: "divider" }}
              >
                <Box
                  sx={{
                    display: "grid",
                    gridTemplateColumns: "repeat(3, minmax(72px, 1fr))",
                    gap: 0.75,
                    minWidth: 0,
                  }}
                >
                  {SENSOR_RIG_CREATE_FIELDS.map((field) => (
                    <TextField
                      key={field.key}
                      size="small"
                      fullWidth
                      type={field.type}
                      label={field.label}
                      value={sensorRigForm[field.key]}
                      sx={COMPACT_FIELD_SX}
                      inputProps={field.type === "number" ? { min: 0.01, step: 0.01 } : undefined}
                      InputProps={
                        field.adornment
                          ? {
                              endAdornment: (
                                <InputAdornment position="end">{field.adornment}</InputAdornment>
                              ),
                            }
                          : undefined
                      }
                      onChange={(event) =>
                        setSensorRigForm((form) => ({
                          ...form,
                          [field.key]: event.target.value,
                        }))
                      }
                    />
                  ))}
                </Box>
                <Stack direction="row" justifyContent="flex-end">
                  <ActionIconButton
                    variant="add"
                    title={savingSensorRig ? "Saving…" : "Create Sensor Rig"}
                    color="primary"
                    loading={savingSensorRig}
                    onClick={() => {
                      void handleCreateSensorRig();
                    }}
                  />
                </Stack>
              </Stack>
            )}
          </WarehouseDrawerSection>

          <WarehouseDrawerSection
            title="Dock Station"
            info="Optional local-frame anchor for takeoff, return, and exploration missions."
          >
            <WarehouseDockPanel
              embedded
              warehouseMapId={selectedWarehouseMapId}
              selectedDockId={selectedDockId}
              onSelectedDockIdChange={setSelectedDockId}
              getToken={getToken}
              onError={addError}
            />
          </WarehouseDrawerSection>

          <WarehouseDrawerSection
            title="Default Flight Parameters"
            info="Controls aisle spacing, scan layers, ceiling clearance, and rack-facing view behavior for automated warehouse scan missions."
            action={loadingMissionDefaults ? <CircularProgress size={16} /> : null}
          >
            {missionDefaultsDraft ? (
              <>
                <Box
                  sx={{
                    display: "grid",
                    gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
                    gap: 1,
                  }}
                >
                  {WAREHOUSE_MISSION_DEFAULT_COLUMN_ROWS.map((columnRows, columnIndex) => (
                    <Box key={`warehouse-default-column-${columnIndex}`} sx={{ minWidth: 0, overflowX: "hidden" }}>
                      <Table size="small" sx={{ width: "100%", tableLayout: "fixed" }}>
                        <TableHead>
                          <TableRow>
                            <TableCell sx={{ width: "58%", pr: 0.75, py: 0.5, fontSize: "0.7rem" }}>
                              Parameter
                            </TableCell>
                            <TableCell sx={{ width: "42%", pl: 0.5, py: 0.5, fontSize: "0.7rem" }}>
                              Value
                            </TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {columnRows.map((row) => (
                            <TableRow key={row.key}>
                              <TableCell
                                sx={{
                                  width: "58%",
                                  py: 0.5,
                                  pr: 0.75,
                                  fontSize: "0.7rem",
                                  whiteSpace: "normal",
                                  wordBreak: "break-word",
                                  lineHeight: 1.2,
                                }}
                              >
                                {row.label}
                              </TableCell>
                              <TableCell sx={{ width: "42%", minWidth: 0, py: 0.5, pl: 0.5 }}>
                                {row.kind === "select" ? (
                                  <TextField
                                    select
                                    size="small"
                                    value={missionDefaultsDraft[row.key]}
                                    onChange={(event) => {
                                      handleMissionDefaultsDraftChange(row.key, event.target.value);
                                    }}
                                    sx={MISSION_DEFAULT_VALUE_SX}
                                  >
                                    {row.options.map((option) => (
                                      <MenuItem
                                        key={option.value}
                                        value={option.value}
                                        sx={{ fontSize: "0.68rem", py: 0.25 }}
                                      >
                                        {option.label}
                                      </MenuItem>
                                    ))}
                                  </TextField>
                                ) : (
                                  <TextField
                                    size="small"
                                    type="number"
                                    value={missionDefaultsDraft[row.key]}
                                    placeholder={row.placeholder}
                                    onChange={(event) => {
                                      handleMissionDefaultsDraftChange(row.key, event.target.value);
                                    }}
                                    inputProps={{ min: row.min, step: row.step }}
                                    sx={MISSION_DEFAULT_VALUE_SX}
                                  />
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </Box>
                  ))}
                </Box>
                <Stack direction="row" justifyContent="flex-end" sx={{ mt: 1.5 }}>
                  <ActionIconButton
                    variant="upgrade"
                    title={savingMissionDefaults ? "Updating Parameters…" : "Update Parameters"}
                    color="primary"
                    loading={savingMissionDefaults}
                    onClick={() => {
                      void handleUpdateMissionDefaults();
                    }}
                  />
                </Stack>
                {missionDefaultsMessage && (
                  <Alert severity="success" sx={{ mt: 1.5 }}>
                    {missionDefaultsMessage}
                  </Alert>
                )}
              </>
            ) : (
              <Alert severity="info">Warehouse mission defaults are unavailable right now.</Alert>
            )}
          </WarehouseDrawerSection>
        </Stack>
      </TaskPreflightCommandsDrawer>

      <TaskPreflightCommandsDrawer
        open={warehouseMissionDrawer.open}
        onOpenChange={handleWarehouseMissionOpenChange}
        title="Warehouse Missions"
        subtitle="Exploration, manual mapping, and scan results"
        tabLabel="FLY"
        tabIcon={<ExploreRoundedIcon fontSize="small" />}
        edgeTabIndex={1}
        edgeTabCount={3}
        paperSx={{ width: { xs: "min(100vw, 520px)", sm: 540, md: 560 } }}
      >
        <Stack spacing={2}>
          <WarehouseDrawerSection
            title="Exploration"
            info="Frontier mode uses the ROS nvblox ESDF map and returns before reserve battery."
          >
            <WarehouseExplorationPanel
              embedded
              warehouseMapId={selectedWarehouseMapId}
              selectedDockId={selectedDockId}
              warehouseName={selectedWarehouseMapName ?? undefined}
              getToken={getToken}
              onLaunch={handleExplorationLaunch}
              onError={handleExplorationError}
            />
          </WarehouseDrawerSection>

          <WarehouseDrawerSection
            title="Manual Warehouse Mapping"
            info="Start a controlled keyboard flight, start ROS mapping, fly the inbound area manually, then stop mapping after landing."
          >
            <WarehouseManualMappingPanel
              embedded
              activeFlightId={activeFlightId}
              missionStatus={missionStatus}
              telemetry={telemetry}
              wsConnected={wsConnected}
              droneConnected={droneConnected}
              warehouseMapId={selectedWarehouseMapId}
              sensorRigId={selectedSensorRigId}
              dockId={selectedDockId}
              setPendingFlightId={setPendingFlightId}
              onPreflightRun={setWarehousePreflightRun}
              onMessage={setScanLaunchMessage}
              onError={addError}
              onScanResultReady={handleScanResultReady}
            />
          </WarehouseDrawerSection>

          <WarehouseDrawerSection
            title="Previous Scan Results"
            info="Finished warehouse scans appear here after automated scans, exploration, or manual mapping stop. Use View in 3D Map to load a result in the main viewer."
            action={loadingScannedMaps ? <CircularProgress size={16} /> : null}
            showDivider={false}
          >
            <Stack direction="row" spacing={1} alignItems="flex-start">
              <TextField
                select
                disabled={!loadingScannedMaps && scannedMaps.length === 0}
                size="small"
                label="Scanned Maps"
                value={selectedScannedMap ? String(selectedScannedMap.job_id) : ""}
                onChange={(event) => {
                  const raw = event.target.value;
                  setSelectedMapJobId(raw ? Number(raw) : null);
                }}
                helperText={
                  selectedScannedMap
                    ? selectedScannedMap.status === "failed" && selectedScannedMap.error
                      ? selectedScannedMap.error
                      : `${getWarehouseName(selectedScannedMap)} (#${getWarehouseMapId(selectedScannedMap)})${
                          selectedReferenceJobId != null ? ` • Ref #${selectedReferenceJobId}` : ""
                        }`
                    : undefined
                }
                sx={{ flex: 1, minWidth: 0 }}
              >
                {scannedMaps.length === 0 && (
                  <MenuItem value="" disabled>
                    No scanned maps available
                  </MenuItem>
                )}
                {scannedMaps.map((map) => (
                  <MenuItem key={map.job_id} value={String(map.job_id)}>
                    {`${getWarehouseName(map)} • ${map.source === "simulation" ? "simulation" : "real flight"} • v${map.model_version} • ${map.status} • ${formatTimestamp(map.created_at)}`}
                  </MenuItem>
                ))}
              </TextField>
              <Stack direction="row" spacing={0.25} alignItems="center" sx={{ flexShrink: 0, pt: 2.25 }}>
                <ActionIconButton
                  variant="map"
                  title="View in 3D Map"
                  color="primary"
                  disabled={!selectedScannedMap}
                  onClick={showSelectedScanInViewer}
                />
                <ActionIconButton
                  variant="refresh"
                  title="Refresh Scan Results"
                  loading={loadingScannedMaps}
                  onClick={() => {
                    void loadScannedMaps();
                  }}
                />
                <ActionIconButton
                  variant="check"
                  title="Use as Reference"
                  color={
                    selectedReferenceJobId != null &&
                    selectedScannedMap?.job_id === selectedReferenceJobId
                      ? "primary"
                      : "default"
                  }
                  disabled={!selectedScannedMap}
                  onClick={() => {
                    setSelectedReferenceJobId(selectedScannedMap?.job_id ?? null);
                  }}
                />
                <ActionIconButton
                  variant="delete"
                  title={deletingScannedMap ? "Deleting…" : "Delete Result"}
                  color="error"
                  loading={deletingScannedMap}
                  disabled={!selectedScannedMap}
                  onClick={() => {
                    void handleDeleteScannedMap();
                  }}
                />
              </Stack>
            </Stack>
            <WarehouseMapQualityPanel
              jobId={selectedScannedMap?.job_id ?? null}
              getToken={getToken}
              onError={addError}
            />
          </WarehouseDrawerSection>
        </Stack>
      </TaskPreflightCommandsDrawer>

      <TaskPreflightCommandsDrawer
        open={warehousePreflightDrawer.open}
        onOpenChange={handleWarehousePreflightOpenChange}
        edgeTabIndex={2}
        edgeTabCount={3}
      >
        <MissionPreflightPanel
          apiBase={apiBase}
          missionType="warehouse_scan"
          preflightRun={warehousePreflightRun}
          telemetry={telemetry}
          title="Warehouse Preflight"
        />
        <MissionCommandPanel
          telemetry={telemetry}
          droneConnected={droneConnected}
          missionStatus={missionStatus}
          activeFlightId={activeFlightId}
          apiBase={apiBase}
          title="Warehouse Commands"
        />
      </TaskPreflightCommandsDrawer>
    </>
  );
}
