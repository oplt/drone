import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
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
import Header from "../../../components/dashboard/Header";
import { ErrorAlerts } from "../../../components/dashboard/tasks/ErrorAlerts";
import { MissionCommandPanel } from "../../../components/dashboard/tasks/MissionCommandPanel";
import { MissionPreflightPanel } from "../../../components/dashboard/tasks/MissionPreflightPanel";
import { MissionStatusChips } from "../../../components/dashboard/tasks/MissionStatusChips";
import { MissionVideoPanel } from "../../../components/dashboard/tasks/MissionVideoPanel";
import { getToken } from "../../../auth";
import { useAutoStartVideo } from "../../../hooks/useAutoStartVideo";
import { useErrors } from "../../../hooks/useErrors";
import { useMissionWebsocketRuntime } from "../../../hooks/useMissionWebsocketRuntime";
import {
  getWarehouseMissionDefaults,
  listWarehouseScannedMaps,
  startWarehouseScan,
  type MissionLifecycleState,
  type WarehouseMissionDefaultsResponse,
  type WarehouseScannedMapResponse,
  updateWarehouseMissionDefaults,
} from "../../../utils/api";

type WarehouseMapOut = {
  id: number;
  name: string;
  area_m2: number | null;
  created_at: string;
  polygon_local_m: [number, number][];
};

type CreateMapForm = {
  name: string;
  width_m: string;
  length_m: string;
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
};

const VIDEO_RETRY_DELAY_MS = 5000;
const SCANNED_MAP_REFRESH_MS = 30000;

const getWarehouseMapId = (map: unknown): number | null => {
  const raw = (map as any)?.warehouse_map_id ?? (map as any)?.field_id ?? null;
  return typeof raw === "number" ? raw : raw ? Number(raw) : null;
};

const getWarehouseName = (map: unknown): string => {
  const raw = (map as any)?.warehouse_name ?? (map as any)?.field_name ?? null;
  return typeof raw === "string" && raw.trim().length > 0 ? raw.trim() : "Warehouse";
};

const toMessage = (error: unknown): string =>
  error instanceof Error ? error.message : "Request failed";

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
  const splitIndex = Math.ceil(WAREHOUSE_MISSION_DEFAULT_ROWS.length / 2);
  return [
    WAREHOUSE_MISSION_DEFAULT_ROWS.slice(0, splitIndex),
    WAREHOUSE_MISSION_DEFAULT_ROWS.slice(splitIndex),
  ];
})();

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
  const [scannedMaps, setScannedMaps] = useState<WarehouseScannedMapResponse[]>([]);
  const [loadingScannedMaps, setLoadingScannedMaps] = useState(false);
  const [selectedMapJobId, setSelectedMapJobId] = useState<number | null>(null);

  // Warehouse maps (footprints) — separate from scanned results
  const [warehouseMaps, setWarehouseMaps] = useState<WarehouseMapOut[]>([]);
  const [loadingWarehouseMaps, setLoadingWarehouseMaps] = useState(false);
  const [selectedWarehouseMapId, setSelectedWarehouseMapId] = useState<number | null>(null);
  const [createMapForm, setCreateMapForm] = useState<CreateMapForm>({ name: "", width_m: "", length_m: "" });
  const [creatingMap, setCreatingMap] = useState(false);
  const [showCreateMap, setShowCreateMap] = useState(false);
  const [tilesetUrl, setTilesetUrl] = useState<string | null>(null);
  const [loadingTileset, setLoadingTileset] = useState(false);
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
  });

  const { startingVideo, streamKey: autoStreamKey } = useAutoStartVideo({
    apiBase,
    getToken,
    enabled: Boolean(activeFlightId && droneConnected),
    onError: addError,
    resetKey: activeFlightId ?? "none",
  });

  const selectedScannedMap = useMemo(
    () =>
      scannedMaps.find((map) => map.job_id === selectedMapJobId) ??
      scannedMaps[0] ??
      null,
    [scannedMaps, selectedMapJobId],
  );

  const toAbsoluteAssetUrl = useCallback(
    (rawUrl: string): string => {
      if (/^https?:\/\//i.test(rawUrl)) return rawUrl;
      const normalizedPath = rawUrl.startsWith("/") ? rawUrl : `/${rawUrl}`;
      return `${apiBase}${normalizedPath}`;
    },
    [apiBase],
  );

  const resolveTilesetUrlFromAssets = useCallback(
    async (assets: WarehouseScannedMapResponse["assets"]): Promise<string | null> => {
      const tilesetAsset = assets.find(
        (asset) => asset.type === "TILESET_3D" && typeof asset.url === "string",
      );
      if (!tilesetAsset?.url) return null;

      const token = getToken();
      if (token && Number.isFinite(tilesetAsset.id)) {
        try {
          const signedRes = await fetch(
            `${apiBase}/mapping/assets/${tilesetAsset.id}/signed-url?ttl_seconds=3600&path=tileset.json`,
            { headers: { Authorization: `Bearer ${token}` } },
          );
          if (signedRes.ok) {
            const signedData = (await signedRes.json()) as { url?: string };
            if (typeof signedData?.url === "string" && signedData.url.trim()) {
              return signedData.url;
            }
          }
        } catch {
          // Fallback to the stored asset URL when signing fails.
        }
      }

      const absolute = toAbsoluteAssetUrl(tilesetAsset.url);
      if (/\.json(\?|$)/i.test(absolute)) {
        return absolute;
      }
      return `${absolute.replace(/\/+$/, "")}/tileset.json`;
    },
    [apiBase, toAbsoluteAssetUrl],
  );

  const loadScannedMaps = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    setLoadingScannedMaps(true);
    try {
      const records = await listWarehouseScannedMaps(token, apiBase);
      setScannedMaps(records);
      setSelectedMapJobId((current) => {
        if (current != null && records.some((record) => record.job_id === current)) {
          return current;
        }
        return records[0]?.job_id ?? null;
      });
    } catch (error) {
      addError(`Scanned warehouse maps could not be loaded: ${toMessage(error)}`);
    } finally {
      setLoadingScannedMaps(false);
    }
  }, [addError, apiBase]);

  const loadMissionDefaults = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    setLoadingMissionDefaults(true);
    try {
      const defaults = await getWarehouseMissionDefaults(token, apiBase);
      setMissionDefaultsDraft(toWarehouseMissionDefaultsDraft(defaults));
    } catch (error) {
      addError(`Warehouse mission defaults could not be loaded: ${toMessage(error)}`);
    } finally {
      setLoadingMissionDefaults(false);
    }
  }, [addError, apiBase]);

  const loadWarehouseMaps = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoadingWarehouseMaps(true);
    try {
      const res = await fetch(`${apiBase}/warehouse/maps`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const maps = (await res.json()) as WarehouseMapOut[];
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
  }, [addError, apiBase]);

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
      const res = await fetch(`${apiBase}/warehouse/maps`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ name, width_m: width, length_m: length }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error((detail as any)?.detail ?? `HTTP ${res.status}`);
      }
      const created = (await res.json()) as WarehouseMapOut;
      setCreateMapForm({ name: "", width_m: "", length_m: "" });
      setShowCreateMap(false);
      await loadWarehouseMaps();
      setSelectedWarehouseMapId(created.id);
    } catch (error) {
      addError(`Could not create warehouse map: ${toMessage(error)}`);
    } finally {
      setCreatingMap(false);
    }
  }, [addError, apiBase, createMapForm, loadWarehouseMaps]);

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
    const handle = window.setInterval(() => {
      void loadScannedMaps();
    }, SCANNED_MAP_REFRESH_MS);
    return () => window.clearInterval(handle);
  }, [loadScannedMaps]);

  useEffect(() => {
    let ignore = false;

    if (!selectedScannedMap) {
      setTilesetUrl(null);
      return () => {
        ignore = true;
      };
    }

    setLoadingTileset(true);
    void resolveTilesetUrlFromAssets(selectedScannedMap.assets)
      .then((url) => {
        if (!ignore) {
          setTilesetUrl(url);
        }
      })
      .catch((error) => {
        if (!ignore) {
          setTilesetUrl(null);
          addError(`Selected 3D warehouse map could not be opened: ${toMessage(error)}`);
        }
      })
      .finally(() => {
        if (!ignore) {
          setLoadingTileset(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [addError, resolveTilesetUrlFromAssets, selectedScannedMap]);

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

    const warehouseMap = warehouseMaps.find((m) => m.id === selectedWarehouseMapId);

    setStartingScan(true);
    setScanLaunchMessage(null);
    try {
      const launch = await startWarehouseScan(
        {
          warehouse_map_id: selectedWarehouseMapId,
          mission_name: `Warehouse Scan${warehouseMap ? ` - ${warehouseMap.name}` : ""}`,
          // Link to the most recent scanned result for this map as reference, if available
          reference_mapping_job_id: scannedMaps.find(
            (m) => getWarehouseMapId(m) === selectedWarehouseMapId
          )?.job_id ?? undefined,
        },
        token,
        apiBase,
      );

      setPendingFlightId(launch.mission.flight_id);
      setScanLaunchMessage(
        `Started ${launch.mission.mission_name} in ${getWarehouseName(launch)}. Preflight ${launch.preflight.overall_status}.`,
      );
      void loadScannedMaps();
    } catch (error) {
      addError(`Warehouse scan could not be started: ${toMessage(error)}`);
    } finally {
      setStartingScan(false);
    }
  }, [addError, apiBase, loadScannedMaps, scannedMaps, selectedWarehouseMapId, warehouseMaps, setPendingFlightId]);

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
      const saved = await updateWarehouseMissionDefaults(payload, token, apiBase);
      setMissionDefaultsDraft(toWarehouseMissionDefaultsDraft(saved));
      setMissionDefaultsMessage("Warehouse mission defaults updated.");
    } catch (error) {
      addError(`Warehouse mission defaults could not be updated: ${toMessage(error)}`);
    } finally {
      setSavingMissionDefaults(false);
    }
  }, [addError, apiBase, missionDefaultsDraft]);

  const missionName =
    missionStatus?.mission_lifecycle?.mission_name ??
    missionStatus?.mission_name ??
    "No active warehouse mission";
  const missionState = missionStatus?.mission_lifecycle?.state ?? "idle";
  const telemetryConnections = missionStatus?.telemetry?.active_connections;
  const videoStatus = startingVideo
    ? "Starting"
    : videoError
      ? "Unavailable"
      : droneConnected
        ? "Ready"
        : "Offline";

  const dronePosition =
    (telemetry as any)?.position ?? missionStatus?.telemetry?.position ?? null;

  return (
    <>
      <Header />
      <Paper
        sx={{
          width: "100%",
          p: 3,
          borderRadius: 1,
          background:
            "linear-gradient(135deg, hsla(174, 50%, 95%, 0.8), hsla(36, 40%, 96%, 0.9))",
          border: "1px solid hsla(174, 30%, 40%, 0.2)",
          '[data-mui-color-scheme="dark"] &': {
            background:
              "linear-gradient(135deg, hsla(168, 24%, 14%, 0.94), hsla(28, 22%, 13%, 0.96))",
            borderColor: "hsla(168, 22%, 36%, 0.3)",
          },
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
            <Typography variant="h5">Warehouse Operations</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Launch warehouse scans, monitor mission state, stream the live
              camera, and review recorded 3D warehouse maps.
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

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "1fr",
              md: "minmax(0, 1.15fr) minmax(340px, 0.85fr)",
            },
            gap: 3,
            alignItems: "start",
          }}
        >
          <Stack sx={{ minWidth: 0 }} spacing={2}>
            <Stack spacing={1}>
              <Paper
                variant="outlined"
                sx={{
                  p: 2,
                  borderRadius: 1,
                  borderColor: "hsla(174, 30%, 40%, 0.25)",
                  background: "hsla(0, 0%, 100%, 0.72)",
                  '[data-mui-color-scheme="dark"] &': {
                    background: "hsla(20, 16%, 12%, 0.92)",
                    borderColor: "hsla(168, 22%, 36%, 0.3)",
                  },
                }}
              >
                <Stack
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                  sx={{ mb: 1.5 }}
                >
                  <Typography variant="subtitle1">Warehouse 3D Map</Typography>
                  {loadingTileset && <CircularProgress size={16} />}
                </Stack>

                {tilesetUrl ? (
                  <Box
                    sx={{
                      height: 400,
                      borderRadius: 1,
                      bgcolor: "rgba(0,0,0,0.86)",
                      color: "common.white",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      textAlign: "center",
                      px: 3,
                      gap: 1,
                    }}
                  >
                    <Typography variant="body2" sx={{ opacity: 0.7 }}>
                      3D tileset ready
                    </Typography>
                    <Typography variant="caption" sx={{ opacity: 0.5, wordBreak: "break-all" }}>
                      {tilesetUrl}
                    </Typography>
                  </Box>
                ) : (
                  <Box
                    sx={{
                      height: 160,
                      borderRadius: 1,
                      bgcolor: "rgba(0, 0, 0, 0.06)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      textAlign: "center",
                      px: 3,
                    }}
                  >
                    <Typography variant="body2" color="text.secondary">
                      {loadingScannedMaps || loadingTileset
                        ? "Loading 3D map..."
                        : "No 3D scan result selected."}
                    </Typography>
                  </Box>
                )}

                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: "block", mt: 1.25 }}
                >
                  {selectedScannedMap
                    ? `${getWarehouseName(selectedScannedMap)} • model v${selectedScannedMap.model_version} • ${formatTimestamp(
                        selectedScannedMap.created_at,
                      )}`
                    : "No scanned warehouse map selected."}
                </Typography>
              </Paper>

              <Paper
                variant="outlined"
                sx={{
                  p: 2,
                  borderRadius: 2,
                  borderColor: "hsla(174, 30%, 40%, 0.25)",
                  background: "hsla(0, 0%, 100%, 0.72)",
                  '[data-mui-color-scheme="dark"] &': {
                    background: "hsla(20, 16%, 12%, 0.92)",
                    borderColor: "hsla(168, 22%, 36%, 0.3)",
                  },
                }}
              >
                <Stack spacing={1.2}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <Typography variant="subtitle1">Warehouse Map</Typography>
                    {loadingWarehouseMaps && <CircularProgress size={16} />}
                  </Stack>

                  <Typography variant="caption" color="text.secondary">
                    Select the warehouse footprint. The drone scans the area using
                    local metric coordinates — no GPS required.
                  </Typography>

                  <TextField
                    select
                    fullWidth
                    size="small"
                    label="Warehouse Map"
                    value={selectedWarehouseMapId != null ? String(selectedWarehouseMapId) : ""}
                    onChange={(event) => {
                      const raw = event.target.value;
                      setSelectedWarehouseMapId(raw ? Number(raw) : null);
                    }}
                    disabled={loadingWarehouseMaps}
                    helperText={
                      warehouseMaps.length === 0
                        ? "No maps yet — create one below."
                        : selectedWarehouseMapId
                          ? (() => {
                              const m = warehouseMaps.find((x) => x.id === selectedWarehouseMapId);
                              return m
                                ? `${m.area_m2 != null ? `${Math.round(m.area_m2)} m²` : "area unknown"}`
                                : `Map #${selectedWarehouseMapId}`;
                            })()
                          : "Choose a warehouse footprint"
                    }
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

                  <Stack direction="row" spacing={1}>
                    <Button
                      variant="outlined"
                      size="small"
                      disabled={loadingWarehouseMaps}
                      onClick={() => { void loadWarehouseMaps(); }}
                      sx={{ flex: "none" }}
                    >
                      Refresh
                    </Button>
                    <Button
                      variant={showCreateMap ? "contained" : "outlined"}
                      size="small"
                      onClick={() => setShowCreateMap((v) => !v)}
                      sx={{ flex: 1 }}
                    >
                      {showCreateMap ? "Cancel" : "+ New Map"}
                    </Button>
                  </Stack>

                  {showCreateMap && (
                    <Stack
                      spacing={1}
                      sx={{
                        p: 1.5,
                        borderRadius: 1,
                        border: "1px solid",
                        borderColor: "divider",
                      }}
                    >
                      <Typography variant="caption" color="text.secondary">
                        Enter the physical dimensions of the warehouse floor. The
                        origin (0, 0) will be the drone's takeoff position.
                      </Typography>
                      <TextField
                        size="small"
                        label="Map name"
                        fullWidth
                        value={createMapForm.name}
                        onChange={(e) =>
                          setCreateMapForm((f) => ({ ...f, name: e.target.value }))
                        }
                        placeholder="e.g. Aisle A–F"
                      />
                      <Stack direction="row" spacing={1}>
                        <TextField
                          size="small"
                          label="Width"
                          type="number"
                          inputProps={{ min: 0.1, step: 0.5 }}
                          InputProps={{
                            endAdornment: <InputAdornment position="end">m</InputAdornment>,
                          }}
                          value={createMapForm.width_m}
                          onChange={(e) =>
                            setCreateMapForm((f) => ({ ...f, width_m: e.target.value }))
                          }
                        />
                        <TextField
                          size="small"
                          label="Length"
                          type="number"
                          inputProps={{ min: 0.1, step: 0.5 }}
                          InputProps={{
                            endAdornment: <InputAdornment position="end">m</InputAdornment>,
                          }}
                          value={createMapForm.length_m}
                          onChange={(e) =>
                            setCreateMapForm((f) => ({ ...f, length_m: e.target.value }))
                          }
                        />
                      </Stack>
                      <Button
                        variant="contained"
                        size="small"
                        disabled={creatingMap}
                        onClick={() => { void handleCreateWarehouseMap(); }}
                        fullWidth
                      >
                        {creatingMap ? (
                          <Stack direction="row" spacing={1} alignItems="center">
                            <CircularProgress size={14} color="inherit" />
                            <span>Creating…</span>
                          </Stack>
                        ) : (
                          "Create Map"
                        )}
                      </Button>
                    </Stack>
                  )}
                </Stack>
              </Paper>

              <Paper
                variant="outlined"
                sx={{
                  p: 2,
                  borderRadius: 2,
                  borderColor: "hsla(174, 30%, 40%, 0.25)",
                  background: "hsla(0, 0%, 100%, 0.72)",
                  '[data-mui-color-scheme="dark"] &': {
                    background: "hsla(20, 16%, 12%, 0.92)",
                    borderColor: "hsla(168, 22%, 36%, 0.3)",
                  },
                }}
              >
                <Stack spacing={1.2}>
                  <Stack
                    direction="row"
                    alignItems="center"
                    justifyContent="space-between"
                  >
                    <Typography variant="subtitle1">Previous Scan Results</Typography>
                    {loadingScannedMaps && <CircularProgress size={16} />}
                  </Stack>
                  <TextField
                    select
                    fullWidth
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
                        ? `Area ${getWarehouseName(selectedScannedMap)} (#${getWarehouseMapId(selectedScannedMap) ?? "?"})`
                        : "Select a stored 3D result to view in the map above."
                    }
                  >
                    {scannedMaps.length === 0 && (
                      <MenuItem value="" disabled>
                        No scanned maps available
                      </MenuItem>
                    )}
                    {scannedMaps.map((map) => (
                      <MenuItem key={map.job_id} value={String(map.job_id)}>
                        {`${getWarehouseName(map)} • v${map.model_version} • ${formatTimestamp(map.created_at)}`}
                      </MenuItem>
                    ))}
                  </TextField>
                  <Button
                    variant="outlined"
                    size="small"
                    disabled={loadingScannedMaps}
                    onClick={() => {
                      void loadScannedMaps();
                    }}
                  >
                    Refresh Scan Results
                  </Button>
                </Stack>
              </Paper>

              <Paper
                variant="outlined"
                sx={{
                  p: 2,
                  borderRadius: 2,
                  borderColor: "hsla(174, 30%, 40%, 0.25)",
                  background: "hsla(0, 0%, 100%, 0.72)",
                  '[data-mui-color-scheme="dark"] &': {
                    background: "hsla(20, 16%, 12%, 0.92)",
                    borderColor: "hsla(168, 22%, 36%, 0.3)",
                  },
                }}
              >
                <Stack
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                  sx={{ mb: 1 }}
                >
                  <Typography variant="subtitle1">
                    Default Flight Parameters
                  </Typography>
                  {loadingMissionDefaults && <CircularProgress size={16} />}
                </Stack>

                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: "block", mb: 1.5 }}
                >
                  These values control aisle spacing, scan layers, ceiling
                  clearance, and rack-facing view behavior for new warehouse
                  scan missions.
                </Typography>

                {missionDefaultsDraft ? (
                  <>
                    <Box
                      sx={{
                        display: "grid",
                        gridTemplateColumns: {
                          xs: "1fr",
                          lg: "repeat(2, minmax(0, 1fr))",
                        },
                        gap: 1,
                      }}
                    >
                      {WAREHOUSE_MISSION_DEFAULT_COLUMN_ROWS.map((columnRows, columnIndex) => (
                        <Box
                          key={`warehouse-default-column-${columnIndex}`}
                          sx={{ minWidth: 0, overflowX: "hidden" }}
                        >
                          <Table size="small" sx={{ width: "100%", tableLayout: "fixed" }}>
                            <TableHead>
                              <TableRow>
                                <TableCell sx={{ width: "56%", pr: 1, whiteSpace: "nowrap" }}>
                                  Parameter
                                </TableCell>
                                <TableCell sx={{ width: "44%", pl: 1 }}>Value</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {columnRows.map((row) => (
                                <TableRow key={row.key}>
                                  <TableCell
                                    sx={{
                                      width: "56%",
                                      py: 0.9,
                                      pr: 1,
                                      whiteSpace: "normal",
                                      wordBreak: "break-word",
                                    }}
                                  >
                                    {row.label}
                                  </TableCell>
                                  <TableCell sx={{ width: "44%", minWidth: 0, py: 0.9, pl: 1 }}>
                                    {row.kind === "select" ? (
                                      <TextField
                                        select
                                        size="small"
                                        value={missionDefaultsDraft[row.key]}
                                        onChange={(event) => {
                                          handleMissionDefaultsDraftChange(
                                            row.key,
                                            event.target.value,
                                          );
                                        }}
                                        sx={{ width: "100%", maxWidth: 148, ml: "auto" }}
                                      >
                                        {row.options.map((option) => (
                                          <MenuItem
                                            key={option.value}
                                            value={option.value}
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
                                          handleMissionDefaultsDraftChange(
                                            row.key,
                                            event.target.value,
                                          );
                                        }}
                                        inputProps={{
                                          min: row.min,
                                          step: row.step,
                                        }}
                                        sx={{ width: "100%", maxWidth: 148, ml: "auto" }}
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

                    <Button
                      variant="contained"
                      fullWidth
                      disabled={savingMissionDefaults}
                      onClick={() => {
                        void handleUpdateMissionDefaults();
                      }}
                      sx={{ mt: 1.5 }}
                    >
                      {savingMissionDefaults ? (
                        <Stack direction="row" spacing={1} alignItems="center">
                          <CircularProgress size={18} color="inherit" />
                          <span>Updating Parameters</span>
                        </Stack>
                      ) : (
                        "Update"
                      )}
                    </Button>

                    {missionDefaultsMessage && (
                      <Alert severity="success" sx={{ mt: 1.5 }}>
                        {missionDefaultsMessage}
                      </Alert>
                    )}
                  </>
                ) : (
                  <Alert severity="info">
                    Warehouse mission defaults are unavailable right now.
                  </Alert>
                )}
              </Paper>

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
            </Stack>
          </Stack>

          <Stack sx={{ minWidth: 0 }} spacing={2}>
              <Paper
                variant="outlined"
                sx={{
                  p: 2,
                  borderRadius: 2,
                  borderColor: "hsla(174, 30%, 40%, 0.25)",
                  background: "hsla(0, 0%, 100%, 0.72)",
                  '[data-mui-color-scheme="dark"] &': {
                    background: "hsla(20, 16%, 12%, 0.92)",
                    borderColor: "hsla(168, 22%, 36%, 0.3)",
                  },
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
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Active Flight
                    </Typography>
                    <Typography variant="body1">{activeFlightId ?? "--"}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Telemetry Connections
                    </Typography>
                    <Typography variant="body1">
                      {typeof telemetryConnections === "number"
                        ? telemetryConnections
                        : "--"}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Telemetry
                    </Typography>
                    <Typography variant="body1">
                      {missionStatus?.telemetry?.running ? "Running" : "Stopped"}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Camera Feed
                    </Typography>
                    <Typography variant="body1">{videoStatus}</Typography>
                  </Box>
                </Box>

                {!activeFlightId && (
                  <Alert severity="warning" sx={{ mt: 2 }}>
                    No active warehouse mission is currently being tracked.
                  </Alert>
                )}

                {missionStatus?.mission_lifecycle?.last_error && (
                  <Alert severity="error" sx={{ mt: 2 }}>
                    {missionStatus.mission_lifecycle.last_error}
                  </Alert>
                )}

                <Stack sx={{ mt: 2 }} spacing={1.25}>
                  <Button
                    variant="contained"
                    size="large"
                    disabled={startingScan || !selectedWarehouseMapId}
                    onClick={() => {
                      void handleStartWarehouseScan();
                    }}
                    fullWidth
                  >
                    {startingScan ? (
                      <Stack direction="row" spacing={1} alignItems="center">
                        <CircularProgress size={18} color="inherit" />
                        <span>Starting Flight &amp; Scan</span>
                      </Stack>
                    ) : (
                      "Start Flight & Scan"
                    )}
                  </Button>
                  <Typography variant="caption" color="text.secondary">
                    {selectedWarehouseMapId
                      ? `Will scan warehouse map #${selectedWarehouseMapId}.`
                      : "Select a warehouse map above to enable launch."}
                  </Typography>
                </Stack>
              </Paper>

              <MissionPreflightPanel
                apiBase={apiBase}
                missionType="warehouse_scan"
                preflightRun={null}
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
          </Stack>
        </Box>
      </Paper>
    </>
  );
}