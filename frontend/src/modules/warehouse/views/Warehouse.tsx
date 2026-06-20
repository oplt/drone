import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Alert,
  Box,
  CircularProgress,
  Paper,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";
import ExploreRoundedIcon from "@mui/icons-material/ExploreRounded";
import ChecklistRoundedIcon from "@mui/icons-material/ChecklistRounded";
import Header from "../../../shared/layout/WorkflowHeader";
import { ApiError } from "../../../shared/api/apiError";
import { ErrorAlerts } from "../../../shared/ui/ErrorAlerts";
import {
  MissionVideoPanel,
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
  deleteWarehouseScannedMap,
  listWarehouseScannedMaps,
  startWarehouseScan,
  updateWarehouseMissionDefaults,
} from "../api/warehouseMissionsApi";
import { sendWarehouseFlightCommand } from "../api/warehouseFlightApi";
import { WarehousePreflightChecksPanel } from "../components/WarehousePreflightChecksPanel";
import { WarehouseMapSetupPanel } from "../components/WarehouseMapSetupPanel";
import { WarehouseSensorRigSetupPanel } from "../components/WarehouseSensorRigSetupPanel";
import { WarehouseMissionDefaultsPanel } from "../components/WarehouseMissionDefaultsPanel";
import { useRunWarehousePreflight } from "../hooks/useRunWarehousePreflight";
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
import type {
  WarehouseMapOut,
  WarehouseSensorRig,
  WarehouseSensorRigHealth,
} from "../types";
import { WarehouseDrawerSection } from "../components/WarehouseDrawerSection";
import { WarehouseDockPanel } from "../components/WarehouseDockPanel";
import { WarehouseFlightReadinessRibbon } from "../components/WarehouseFlightReadinessRibbon";
import { WarehouseViewerSection } from "../components/WarehouseViewerSection";
import {
  WarehouseFlyDrawerContent,
  type WarehouseFlyMode,
} from "../components/WarehouseFlyDrawerContent";
import { useWarehouseMapPlacement } from "../hooks/useWarehouseMapPlacement";
import {
  WarehouseSystemStatusStrip,
} from "../components/WarehouseDashboardUi";
import type { WarehouseUiStatus } from "../components/WarehouseStatusBadge";
import {
  WarehouseDeleteConfirmationDialog,
  type WarehouseDeleteTarget,
} from "../components/WarehouseDeleteConfirmationDialog";
import { useWarehouseLiveVoxelMap } from "../hooks/useWarehouseLiveVoxelMap";
import { useWarehouseMappingStack } from "../hooks/useWarehouseMappingStack";
import { useWarehouseScannedMapReplay } from "../hooks/useWarehouseScannedMapReplay";
import { useWarehouseFlightReadiness } from "../hooks/useWarehouseFlightReadiness";
import { useWarehouseMissionRuntimeController } from "../hooks/useWarehouseMissionRuntimeController";
import {
  SCANNED_MAP_REFRESH_MS,
  getWarehouseStartMessage,
  getWarehouseStartPreflight,
  toMessage,
  type CreateMapForm,
  type SensorRigForm,
} from "../warehousePageSupport";
import {
  toWarehouseMissionDefaultsDraft,
  toWarehouseMissionDefaultsPayload,
  type WarehouseMissionDefaultsDraft,
  type WarehouseMissionDefaultsKey,
} from "../warehouseMissionDefaults";

export default function WarehousePage() {
  const warehouseSetupDrawer = useTaskPreflightCommandsDrawer();
  const warehouseChecksDrawer = useTaskPreflightCommandsDrawer();
  const warehouseMissionDrawer = useTaskPreflightCommandsDrawer();

  const closeOtherWarehouseDrawers = useCallback(
    (except: "setup" | "checks" | "mission") => {
      if (except !== "setup") warehouseSetupDrawer.closeDrawer();
      if (except !== "checks") warehouseChecksDrawer.closeDrawer();
      if (except !== "mission") warehouseMissionDrawer.closeDrawer();
    },
    [warehouseChecksDrawer, warehouseMissionDrawer, warehouseSetupDrawer],
  );

  const handleWarehouseSetupOpenChange = useCallback(
    (open: boolean) => {
      warehouseSetupDrawer.onOpenChange(open);
      if (open) closeOtherWarehouseDrawers("setup");
    },
    [closeOtherWarehouseDrawers, warehouseSetupDrawer],
  );

  const handleWarehouseChecksOpenChange = useCallback(
    (open: boolean) => {
      warehouseChecksDrawer.onOpenChange(open);
      if (open) closeOtherWarehouseDrawers("checks");
    },
    [closeOtherWarehouseDrawers, warehouseChecksDrawer],
  );

  const handleWarehouseMissionOpenChange = useCallback(
    (open: boolean) => {
      warehouseMissionDrawer.onOpenChange(open);
      if (open) closeOtherWarehouseDrawers("mission");
    },
    [closeOtherWarehouseDrawers, warehouseMissionDrawer],
  );

  const [scannedMaps, setScannedMaps] = useState<WarehouseScannedMapResponse[]>(
    [],
  );
  const [loadingScannedMaps, setLoadingScannedMaps] = useState(false);
  const [selectedMapJobId, setSelectedMapJobId] = useState<number | null>(null);
  const [viewerMapJobId, setViewerMapJobId] = useState<number | null>(null);

  // Warehouse maps (footprints) — separate from scanned results
  const [warehouseMaps, setWarehouseMaps] = useState<WarehouseMapOut[]>([]);
  const [loadingWarehouseMaps, setLoadingWarehouseMaps] = useState(false);
  const [selectedWarehouseMapId, setSelectedWarehouseMapId] = useState<
    number | null
  >(null);
  const [selectedDockId, setSelectedDockId] = useState<number | null>(null);
  const [creatingMap, setCreatingMap] = useState(false);
  const [deletingWarehouseMap, setDeletingWarehouseMap] = useState(false);
  const [deletingScannedMap, setDeletingScannedMap] = useState(false);
  const [sensorRigs, setSensorRigs] = useState<WarehouseSensorRig[]>([]);
  const [selectedSensorRigId, setSelectedSensorRigId] = useState<number | null>(
    null,
  );
  const [sensorRigHealth, setSensorRigHealth] =
    useState<WarehouseSensorRigHealth | null>(null);
  const [loadingSensorRigs, setLoadingSensorRigs] = useState(false);
  const [savingSensorRig, setSavingSensorRig] = useState(false);
  const [deletingSensorRig, setDeletingSensorRig] = useState(false);
  const [missionDefaultsDraft, setMissionDefaultsDraft] =
    useState<WarehouseMissionDefaultsDraft | null>(null);
  const [loadingMissionDefaults, setLoadingMissionDefaults] = useState(false);
  const [savingMissionDefaults, setSavingMissionDefaults] = useState(false);
  const [missionDefaultsMessage, setMissionDefaultsMessage] = useState<
    string | null
  >(null);
  const [setupTab, setSetupTab] = useState<"map" | "rig" | "dock" | "defaults">(
    "map",
  );
  const [flyMode, setFlyMode] = useState<WarehouseFlyMode>("automated");
  const [mapDetailTab, setMapDetailTab] = useState<
    "layers" | "coordinateSetup"
  >("layers");
  const [deleteTarget, setDeleteTarget] = useState<WarehouseDeleteTarget>(null);

  const [startingScan, setStartingScan] = useState(false);
  const [scanLaunchMessage, setScanLaunchMessage] = useState<string | null>(
    null,
  );

  const sensorRigHealthRequestRef = useRef(0);
  const viewerSectionRef = useRef<HTMLDivElement | null>(null);
  const previousMissionStateRef = useRef<MissionLifecycleState | null>(null);
  const { errors, addError, clearErrors, dismissError } = useErrors();

  const apiBaseRaw = import.meta.env.VITE_API_BASE_URL ?? "";
  const apiBase = (apiBaseRaw || "http://localhost:8000").replace(/\/$/, "");
  const videoToken = getToken();
  const authToken = getToken();
  const localStorageKey = useMemo(
    () => `warehouse.ops.${authToken ? authToken.slice(-12) : "anonymous"}`,
    [authToken],
  );
  const missionLoadedForReadiness =
    selectedWarehouseMapId != null && selectedSensorRigId != null;
  const {
    running: preflightRunning,
    result: warehousePreflight,
    error: preflightError,
    runChecks: runWarehousePreflightChecks,
    passed: warehousePreflightPassed,
  } = useRunWarehousePreflight(authToken);
  const {
    data: warehouseFlightReadiness,
    isLoading: flightReadinessLoading,
    refetch: refetchWarehouseFlightReadiness,
  } = useWarehouseFlightReadiness(authToken, {
    missionLoaded: missionLoadedForReadiness,
    enabled:
      Boolean(authToken) &&
      (warehouseChecksDrawer.open ||
        warehouseMissionDrawer.open ||
        preflightRunning),
    preflightRunning,
  });
  const warehouseMapPlacement = useWarehouseMapPlacement({
    warehouseMapId: selectedWarehouseMapId,
    token: authToken,
    onError: addError,
  });

  const { panelProps: mapPlacementPanelProps } = warehouseMapPlacement;
  const setMapPlacementPickMode = mapPlacementPanelProps.setPickMode;

  useEffect(() => {
    if (mapDetailTab !== "coordinateSetup") {
      setMapPlacementPickMode(false);
    }
  }, [mapDetailTab, setMapPlacementPickMode]);

  useEffect(() => {
    if (selectedWarehouseMapId == null) {
      setMapDetailTab("layers");
    }
  }, [selectedWarehouseMapId]);

  const [flightCommandBusy, setFlightCommandBusy] = useState(false);

  const {
    missionStatus,
    activeFlightId,
    setPendingFlightId,
    telemetry,
    wsConnected,
    droneConnected,
    startingVideo,
    streamKey,
    videoError,
    videoRetryCount,
    handleVideoError,
    handleVideoLoad,
    retryVideo,
  } = useWarehouseMissionRuntimeController({
    apiBase,
    onError: addError,
  });

  const viewerScannedMap = useMemo(
    () => selectScannedMap(scannedMaps, viewerMapJobId),
    [scannedMaps, viewerMapJobId],
  );

  const viewingScanReplay = Boolean(viewerScannedMap) && !activeFlightId;
  const missionState = missionStatus?.mission_lifecycle?.state ?? "idle";
  const liveVoxelMapSessionActive = Boolean(
    activeFlightId && warehousePreflightPassed,
  );

  const liveVoxelMap = useWarehouseLiveVoxelMap(activeFlightId, {
    enabled: Boolean(
      activeFlightId &&
      !viewingScanReplay &&
      !warehouseSetupDrawer.open &&
      !warehouseChecksDrawer.open &&
      !warehouseMissionDrawer.open,
    ),
    token: authToken,
  });

  const { mappingStackStatus } = useWarehouseMappingStack({
    enabled: Boolean(activeFlightId),
    getToken,
  });

  const selectedScannedMap = useMemo(
    () => selectScannedMap(scannedMaps, selectedMapJobId),
    [scannedMaps, selectedMapJobId],
  );

  const scannedMapReplay = useWarehouseScannedMapReplay(
    viewerScannedMap,
    authToken,
    {
      enabled: viewingScanReplay,
    },
  );
  const displayedVoxelMap = viewingScanReplay
    ? scannedMapReplay.state
    : liveVoxelMapSessionActive
      ? liveVoxelMap
      : scannedMapReplay.state;
  const showVoxelMapViewer =
    Boolean(viewerScannedMap) || liveVoxelMapSessionActive;

  const loadScannedMaps = useCallback(
    async (options?: { selectJobId?: number; showInViewer?: boolean }) => {
      const token = getToken();
      if (!token) return [];

      setLoadingScannedMaps(true);
      try {
        const records = await listWarehouseScannedMaps(
          token,
          selectedWarehouseMapId,
        );
        setScannedMaps(records);

        const explicitJobId = options?.selectJobId;
        if (explicitJobId != null) {
          setSelectedMapJobId(explicitJobId);
          if (options?.showInViewer) {
            setViewerMapJobId(explicitJobId);
          }
        } else {
          setSelectedMapJobId((current) => {
            if (
              current != null &&
              records.some((record) => record.job_id === current)
            ) {
              return current;
            }
            return null;
          });
        }
        return records;
      } catch (error) {
        addError(
          `Scanned warehouse maps could not be loaded: ${toMessage(error)}`,
        );
        return [];
      } finally {
        setLoadingScannedMaps(false);
      }
    },
    [addError, selectedWarehouseMapId],
  );

  const handleScanResultReady = useCallback(
    (jobId: number) => {
      void loadScannedMaps({ selectJobId: jobId, showInViewer: true }).then(
        () => {
          viewerSectionRef.current?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        },
      );
      setScanLaunchMessage(
        `Scan result #${jobId} saved to Previous Scan Results.`,
      );
    },
    [loadScannedMaps],
  );

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

  const loadWarehouseMaps = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoadingWarehouseMaps(true);
    try {
      const maps = await listWarehouseMaps(token);
      setWarehouseMaps(maps);
      // Auto-select the first map if nothing is selected yet
      setSelectedWarehouseMapId((current) => {
        if (current != null && maps.some((m) => m.id === current))
          return current;
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
        if (current != null && rigs.some((rig) => rig.id === current))
          return current;
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
      const requestId = sensorRigHealthRequestRef.current + 1;
      sensorRigHealthRequestRef.current = requestId;
      if (!token || sensorRigId == null) {
        setSensorRigHealth(null);
        return;
      }
      try {
        const health = await fetchWarehouseSensorRigHealth(sensorRigId, token);
        if (sensorRigHealthRequestRef.current !== requestId) return;
        setSensorRigHealth(health);
      } catch (error) {
        if (sensorRigHealthRequestRef.current !== requestId) return;
        setSensorRigHealth(null);
        addError(`Sensor rig health could not be loaded: ${toMessage(error)}`);
      }
    },
    [addError],
  );

  const handleCreateWarehouseMap = useCallback(
    async (createMapForm: CreateMapForm) => {
      const token = getToken();
      if (!token) return false;
      const name = createMapForm.name.trim();
      if (!name) {
        addError("Map name is required.");
        return false;
      }
      const width = Number(createMapForm.width_m);
      const length = Number(createMapForm.length_m);
      if (!Number.isFinite(width) || width <= 0) {
        addError("Width must be a positive number.");
        return false;
      }
      if (!Number.isFinite(length) || length <= 0) {
        addError("Length must be a positive number.");
        return false;
      }
      setCreatingMap(true);
      try {
        const created = await createWarehouseMap(
          { name, width_m: width, length_m: length },
          token,
        );
        await loadWarehouseMaps();
        setSelectedWarehouseMapId(created.id);
        setScanLaunchMessage(`Warehouse map "${created.name}" saved.`);
        return true;
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
          addError(
            "Could not create warehouse map: insufficient permissions. Check your account role in the sidebar (needs operator/pilot or higher). Restart the backend if this persists after a recent update.",
          );
        } else {
          addError(`Could not create warehouse map: ${toMessage(error)}`);
        }
        return false;
      } finally {
        setCreatingMap(false);
      }
    },
    [addError, loadWarehouseMaps],
  );

  const handleDeleteWarehouseMap = useCallback(async () => {
    if (selectedWarehouseMapId == null) return;
    const token = getToken();
    if (!token) {
      addError("You must be authenticated to delete warehouse maps.");
      return;
    }
    const map = warehouseMaps.find(
      (item) => item.id === selectedWarehouseMapId,
    );
    const label = map?.name ?? `Map #${selectedWarehouseMapId}`;

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
      setDeleteTarget(null);
    }
  }, [addError, loadWarehouseMaps, selectedWarehouseMapId, warehouseMaps]);

  const handleDeleteScannedMap = useCallback(async () => {
    if (!selectedScannedMap) return;
    const token = getToken();
    if (!token) {
      addError("You must be authenticated to delete scan results.");
      return;
    }
    const jobId = selectedScannedMap.job_id;
    const label = `${getWarehouseName(selectedScannedMap)} (#${jobId})`;

    setDeletingScannedMap(true);
    try {
      await deleteWarehouseScannedMap(jobId, token);
      setSelectedMapJobId((current) => (current === jobId ? null : current));
      setViewerMapJobId((current) => (current === jobId ? null : current));
      await loadScannedMaps();
      setScanLaunchMessage(`Deleted scan result "${label}".`);
    } catch (error) {
      addError(`Could not delete scan result: ${toMessage(error)}`);
    } finally {
      setDeletingScannedMap(false);
      setDeleteTarget(null);
    }
  }, [addError, loadScannedMaps, selectedScannedMap]);

  const handleCreateSensorRig = useCallback(
    async (sensorRigForm: SensorRigForm) => {
      const token = getToken();
      if (!token) return false;
      const name = sensorRigForm.name.trim();
      const cameraModel = sensorRigForm.camera_model.trim();
      if (!name) {
        addError("Sensor rig name is required.");
        return false;
      }
      if (!cameraModel) {
        addError("Camera model is required.");
        return false;
      }
      const baselineRaw = sensorRigForm.stereo_baseline_m.trim();
      const baseline = baselineRaw ? Number(baselineRaw) : null;
      if (
        baselineRaw &&
        (!Number.isFinite(baseline) || Number(baseline) <= 0)
      ) {
        addError("Stereo baseline must be a positive number.");
        return false;
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
            imu_transform_json: {},
          },
          token,
        );
        await loadSensorRigs();
        setSelectedSensorRigId(created.id);
        if (created.calibration_status !== "valid") {
          await updateWarehouseSensorRigCalibration(
            created.id,
            {
              calibration_status: "valid",
              calibration_hash:
                created.calibration_hash ?? `manual-${Date.now()}`,
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
        return true;
      } catch (error) {
        addError(`Could not create sensor rig: ${toMessage(error)}`);
        return false;
      } finally {
        setSavingSensorRig(false);
      }
    },
    [addError, loadSensorRigHealth, loadSensorRigs],
  );

  const handleDeleteSensorRig = useCallback(async () => {
    if (selectedSensorRigId == null) return;
    const token = getToken();
    if (!token) {
      addError("You must be authenticated to delete sensor rigs.");
      return;
    }
    const rig = sensorRigs.find((item) => item.id === selectedSensorRigId);
    const label = rig?.name ?? `Sensor rig #${selectedSensorRigId}`;

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
      setDeleteTarget(null);
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
  }, [
    addError,
    loadSensorRigHealth,
    loadSensorRigs,
    selectedSensorRigId,
    sensorRigs,
  ]);

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
    try {
      const raw = window.localStorage.getItem(localStorageKey);
      if (!raw) return;
      const saved = JSON.parse(raw) as {
        selectedWarehouseMapId?: number | null;
        selectedSensorRigId?: number | null;
        selectedDockId?: number | null;
        setupTab?: "map" | "rig" | "dock" | "defaults" | "inspection";
      };
      if (typeof saved.selectedWarehouseMapId === "number") {
        setSelectedWarehouseMapId(saved.selectedWarehouseMapId);
      }
      if (typeof saved.selectedSensorRigId === "number") {
        setSelectedSensorRigId(saved.selectedSensorRigId);
      }
      if (typeof saved.selectedDockId === "number") {
        setSelectedDockId(saved.selectedDockId);
      }
      if (saved.setupTab && saved.setupTab !== "inspection") {
        setSetupTab(saved.setupTab);
      }
    } catch {
      window.localStorage.removeItem(localStorageKey);
    }
  }, [localStorageKey]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        localStorageKey,
        JSON.stringify({
          selectedWarehouseMapId,
          selectedSensorRigId,
          selectedDockId,
          setupTab,
        }),
      );
    } catch {
      // Local storage is a convenience only.
    }
  }, [
    localStorageKey,
    selectedDockId,
    selectedSensorRigId,
    selectedWarehouseMapId,
    setupTab,
  ]);

  useEffect(() => {
    const refreshVisibleMaps = () => {
      if (!document.hidden) void loadScannedMaps();
    };
    const handle = window.setInterval(
      refreshVisibleMaps,
      SCANNED_MAP_REFRESH_MS,
    );
    document.addEventListener("visibilitychange", refreshVisibleMaps);
    return () => {
      window.clearInterval(handle);
      document.removeEventListener("visibilitychange", refreshVisibleMaps);
    };
  }, [loadScannedMaps]);

  useEffect(() => {
    const state = missionStatus?.mission_lifecycle?.state ?? null;
    const previous = previousMissionStateRef.current;
    if (
      (previous === "running" || previous === "paused") &&
      (state === "completed" || state === "failed" || state === "aborted")
    ) {
      void loadScannedMaps();
    }
    previousMissionStateRef.current = state;
  }, [loadScannedMaps, missionStatus?.mission_lifecycle?.state]);

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
      addError(
        "Select a calibrated warehouse sensor rig before starting the scan.",
      );
      return;
    }

    const warehouseMap = warehouseMaps.find(
      (m) => m.id === selectedWarehouseMapId,
    );

    setStartingScan(true);
    setScanLaunchMessage(null);
    try {
      const launch = await startWarehouseScan(
        {
          warehouse_map_id: selectedWarehouseMapId,
          mission_name: `Warehouse Scan${warehouseMap ? ` - ${warehouseMap.name}` : ""}`,
          sensor_rig_id: selectedSensorRigId,
          dock_id: selectedDockId,
          // Link to the most recent scanned result for this map as reference, if available
          reference_mapping_job_id:
            selectedScannedMap?.job_id ??
            scannedMaps.find(
              (m) => getWarehouseMapId(m) === selectedWarehouseMapId,
            )?.job_id,
        },
        token,
      );

      setPendingFlightId(launch.mission.flight_id);
      void refetchWarehouseFlightReadiness();
      const launchWarehouseName = launch.warehouse_name.trim() || "Warehouse";
      setScanLaunchMessage(
        `Started ${launch.mission.mission_name} in ${launchWarehouseName}. Preflight ${launch.preflight.overall_status}.`,
      );
      void loadScannedMaps();
    } catch (error) {
      const preflight = getWarehouseStartPreflight(error);
      if (preflight) addError(`Latest preflight: ${preflight.overall_status}.`);
      addError(
        `Warehouse scan could not be started: ${getWarehouseStartMessage(error)}`,
      );
    } finally {
      setStartingScan(false);
    }
  }, [
    addError,
    loadScannedMaps,
    refetchWarehouseFlightReadiness,
    scannedMaps,
    selectedDockId,
    selectedScannedMap?.job_id,
    selectedSensorRigId,
    selectedWarehouseMapId,
    sensorRigHealth?.ready,
    warehouseMaps,
    setPendingFlightId,
  ]);

  const handleFlightCommand = useCallback(
    async (command: "pause" | "abort" | "land") => {
      const token = getToken();
      if (!token) {
        addError("You must be authenticated to send flight commands.");
        return;
      }
      setFlightCommandBusy(true);
      try {
        const result = await sendWarehouseFlightCommand(command, token);
        void refetchWarehouseFlightReadiness();
        if (!result.accepted) {
          addError(result.message || `Flight ${command} command failed.`);
        }
      } catch (error) {
        addError(toMessage(error));
      } finally {
        setFlightCommandBusy(false);
      }
    },
    [addError, refetchWarehouseFlightReadiness],
  );

  const handleExplorationLaunch = useCallback(
    (launch: WarehouseMissionLaunchResponse) => {
      setPendingFlightId(launch.mission.flight_id);
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
      if (preflight) addError(`Latest preflight: ${preflight.overall_status}.`);
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
      addError(
        "You must be authenticated to update warehouse mission defaults.",
      );
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
      addError(
        `Warehouse mission defaults could not be updated: ${toMessage(error)}`,
      );
    } finally {
      setSavingMissionDefaults(false);
    }
  }, [addError, missionDefaultsDraft]);

  const missionName =
    missionStatus?.mission_lifecycle?.mission_name ??
    missionStatus?.mission_name ??
    "No active warehouse mission";
  const startScanDisabled =
    startingScan ||
    !selectedWarehouseMapId ||
    selectedSensorRigId == null ||
    sensorRigHealth?.ready !== true ||
    !warehousePreflightPassed;
  const startScanTooltip = !warehousePreflightPassed
    ? "Run preflight checks and wait for them to pass before starting flight."
    : !selectedWarehouseMapId
      ? "Select a warehouse map to enable launch."
      : selectedSensorRigId == null || sensorRigHealth?.ready !== true
        ? "Select a registered sensor rig before starting."
        : !sensorRigHealth?.perception?.ready
          ? "Launch scan — mapping stack and nvblox start with the flight."
          : `Scan warehouse map #${selectedWarehouseMapId}.`;

  const selectedWarehouseMapName = useMemo(() => {
    if (selectedWarehouseMapId == null) return null;
    return (
      warehouseMaps.find((map) => map.id === selectedWarehouseMapId)?.name ??
      null
    );
  }, [selectedWarehouseMapId, warehouseMaps]);

  const visibleScannedMaps = useMemo(() => {
    return scannedMaps.filter((map) => {
      if (selectedWarehouseMapId != null) {
        if (getWarehouseMapId(map) !== selectedWarehouseMapId) return false;
      }
      return true;
    });
  }, [scannedMaps, selectedWarehouseMapId]);

  const systemStatusItems = useMemo(
    () => [
      {
        label: "Drone",
        value: droneConnected ? "Online" : "Offline",
        status: (droneConnected ? "ready" : "blocked") as WarehouseUiStatus,
      },
      {
        label: "Link",
        value: wsConnected ? "Secure" : "Lost",
        status: (wsConnected ? "ready" : "blocked") as WarehouseUiStatus,
      },
      {
        label: "Map",
        value: viewingScanReplay
          ? scannedMapReplay.hasReplay
            ? "Replay"
            : "Empty"
          : activeFlightId
            ? liveVoxelMap.chunks.length > 0
              ? "Live"
              : "Streaming"
            : "None",
        status: (viewingScanReplay
          ? scannedMapReplay.hasReplay
            ? "ready"
            : "waiting"
          : activeFlightId
            ? liveVoxelMap.chunks.length > 0
              ? "ready"
              : "running"
            : "unknown") as WarehouseUiStatus,
      },
      {
        label: "Preflight",
        value: warehousePreflightPassed ? "Ready" : "Blocked",
        status: (warehousePreflightPassed
          ? "ready"
          : "blocked") as WarehouseUiStatus,
      },
      {
        label: "Control",
        value: missionState === "running" ? "Active" : "Idle",
        status: (missionState === "running"
          ? "running"
          : "unknown") as WarehouseUiStatus,
      },
    ],
    [
      activeFlightId,
      droneConnected,
      liveVoxelMap.chunks.length,
      missionState,
      scannedMapReplay.hasReplay,
      viewingScanReplay,
      warehousePreflightPassed,
      wsConnected,
    ],
  );
  const handleManualMappingPreflightRun = useCallback(
    (preflight: PreflightRunResponse | null) => {
      if (preflight)
        setScanLaunchMessage(`Keyboard preflight ${preflight.overall_status}.`);
    },
    [],
  );

  return (
    <>
      <Header />
      <Paper
        sx={{
          width: "100%",
          p: 3,
          borderRadius: 3,
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
            <Typography
              variant="h5"
              sx={{ fontWeight: 800, fontSize: { xs: "1.3rem", md: "1.5rem" } }}
            >
              Warehouse Operations
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Autonomous indoor scan, live telemetry, and 3D mapping
            </Typography>
          </Box>
        </Stack>

        <Box sx={{ mb: 2 }}>
          <WarehouseSystemStatusStrip items={systemStatusItems} />
        </Box>

        <Box sx={{ mb: 2 }}>
          <WarehouseFlightReadinessRibbon
            hasMap={selectedWarehouseMapId != null}
            hasRig={selectedSensorRigId != null}
            hasDock={selectedDockId != null}
            preflight={warehousePreflight}
            droneConnected={droneConnected}
            activeFlightId={activeFlightId}
            sensorRigHealth={sensorRigHealth}
            mappingStatus={missionStatus?.warehouse_mapping}
            liveHealth={liveVoxelMap.health}
          />
        </Box>

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

        <Stack sx={{ minWidth: 0, width: "100%" }} spacing={2}>
          <MissionVideoPanel
            title="Warehouse Camera"
            imgAlt="Warehouse camera stream"
            disconnectedMessage="Waiting for mission video stream"
            frameHeight={600}
            frameSx={{ minHeight: 600, height: 600 }}
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
            onRetry={retryVideo}
          />

          <WarehouseViewerSection
            sectionRef={viewerSectionRef}
            selectorProps={{
              maps: visibleScannedMaps,
              selectedMap: selectedScannedMap,
              loading: loadingScannedMaps,
              disabled: viewingScanReplay && scannedMapReplay.loading,
              deleting: deletingScannedMap,
              onSelect: (jobId) => {
                setSelectedMapJobId(jobId);
                setViewerMapJobId(jobId);
              },
              onRefresh: () => void loadScannedMaps(),
              onDelete: () => {
                if (!selectedScannedMap) return;
                setDeleteTarget({
                  kind: "scan result",
                  label: `${getWarehouseName(selectedScannedMap)} (#${selectedScannedMap.job_id})`,
                  onConfirm: () => void handleDeleteScannedMap(),
                });
              },
            }}
            showViewer={showVoxelMapViewer}
            replayMode={viewingScanReplay}
            viewerProps={{
              flightId: viewingScanReplay
                ? (scannedMapReplay.replayFlightId ??
                  displayedVoxelMap.latestUpdate?.flight_id ??
                  null)
                : (activeFlightId ??
                  displayedVoxelMap.latestUpdate?.flight_id ??
                  null),
              state: displayedVoxelMap,
              cacheMode: viewingScanReplay ? "replay" : undefined,
              mapMode: viewingScanReplay ? "replay" : "live",
              scannedMapId: viewingScanReplay
                ? scannedMapReplay.scannedMapId
                : null,
              onReloadReplay: viewingScanReplay
                ? scannedMapReplay.reloadFromDiskManifest
                : undefined,
              mappingStatus: viewingScanReplay
                ? null
                : (missionStatus?.warehouse_mapping ?? null),
              mappingStackStatus: viewingScanReplay ? null : mappingStackStatus,
              hidden:
                (warehouseSetupDrawer.open ||
                  warehouseChecksDrawer.open ||
                  warehouseMissionDrawer.open) &&
                !warehouseMapPlacement.viewerProps.pickMode &&
                mapDetailTab !== "coordinateSetup",
              mapPlacement: warehouseMapPlacement.viewerProps,
              warehouseMapId: selectedWarehouseMapId,
              mapPlacementPanel: warehouseMapPlacement.panelProps,
              mapDetailTab,
              onMapDetailTabChange: setMapDetailTab,
              onCoordinateSetupError: addError,
              coordinateSetupToken: authToken,
              replayLoading: viewingScanReplay && scannedMapReplay.loading,
              onClearMap: viewingScanReplay
                ? undefined
                : liveVoxelMap.clearMap,
              onToggleStream: viewingScanReplay
                ? undefined
                : liveVoxelMap.toggleStreamPaused,
              streamPaused: viewingScanReplay
                ? false
                : liveVoxelMap.streamPaused,
            }}
          />
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
        paperSx={{
          width: {
            xs: "min(100vw, 560px)",
            sm: 680,
            md: 760,
            lg: 840,
          },
          maxWidth: "100vw",
        }}
      >
        <Stack spacing={2}>
          <Tabs
            value={setupTab}
            onChange={(_, value: "map" | "rig" | "dock" | "defaults") =>
              setSetupTab(value)
            }
            variant="scrollable"
            allowScrollButtonsMobile
          >
            <Tab value="map" label="Map" />
            <Tab value="rig" label="Sensor Rig" />
            <Tab value="dock" label="Dock" />
            <Tab value="defaults" label="Defaults" />
          </Tabs>
          {setupTab === "map" && (
            <WarehouseDrawerSection
              title="Warehouse Map"
              info="Select the warehouse footprint. The drone scans using local metric coordinates — no GPS required. Origin (0, 0) is the takeoff position."
              action={
                loadingWarehouseMaps ? <CircularProgress size={16} /> : null
              }
            >
              <WarehouseMapSetupPanel
                maps={warehouseMaps}
                scannedMaps={scannedMaps}
                selectedId={selectedWarehouseMapId}
                loading={loadingWarehouseMaps}
                creating={creatingMap}
                deleting={deletingWarehouseMap}
                onSelect={(id) => {
                  setSelectedWarehouseMapId(id);
                  setSelectedDockId(null);
                }}
                onRefresh={() => void loadWarehouseMaps()}
                onCreate={handleCreateWarehouseMap}
                onDelete={(map, assetCount) =>
                  setDeleteTarget({
                    kind: "map",
                    label: map?.name ?? `Map #${selectedWarehouseMapId}`,
                    assetCount,
                    onConfirm: () => void handleDeleteWarehouseMap(),
                  })
                }
              />
            </WarehouseDrawerSection>
          )}

          {setupTab === "rig" && (
            <WarehouseDrawerSection
              title="Sensor Rig"
              info="Register calibrated hardware and map sim or real-device ROS source topics to stable /warehouse/contract/* topics."
              action={loadingSensorRigs ? <CircularProgress size={16} /> : null}
            >
              <WarehouseSensorRigSetupPanel
                rigs={sensorRigs}
                selectedId={selectedSensorRigId}
                health={sensorRigHealth}
                loading={loadingSensorRigs}
                saving={savingSensorRig}
                deleting={deletingSensorRig}
                onSelect={setSelectedSensorRigId}
                onRefresh={() => {
                  void loadSensorRigs();
                  void loadSensorRigHealth(selectedSensorRigId);
                }}
                onCalibrate={() => void handleMarkSensorRigCalibrated()}
                onCreate={handleCreateSensorRig}
                onDelete={(rig) =>
                  setDeleteTarget({
                    kind: "sensor rig",
                    label: rig?.name ?? `Sensor rig #${selectedSensorRigId}`,
                    assetCount: 1,
                    onConfirm: () => void handleDeleteSensorRig(),
                  })
                }
              />
            </WarehouseDrawerSection>
          )}

          {setupTab === "dock" && (
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
          )}

          {setupTab === "defaults" && (
            <WarehouseDrawerSection
              title="Default Flight Parameters"
              info="Controls aisle spacing, scan layers, ceiling clearance, and rack-facing view behavior for automated warehouse scan missions."
              action={
                loadingMissionDefaults ? <CircularProgress size={16} /> : null
              }
            >
              <WarehouseMissionDefaultsPanel
                draft={missionDefaultsDraft}
                saving={savingMissionDefaults}
                successMessage={missionDefaultsMessage}
                onChange={handleMissionDefaultsDraftChange}
                onSave={() => void handleUpdateMissionDefaults()}
              />
            </WarehouseDrawerSection>
          )}
        </Stack>
      </TaskPreflightCommandsDrawer>

      <TaskPreflightCommandsDrawer
        open={warehouseChecksDrawer.open}
        onOpenChange={handleWarehouseChecksOpenChange}
        title="Warehouse Checks"
        subtitle="Preflight readiness and system diagnostics"
        tabLabel="CHECKS"
        tabIcon={<ChecklistRoundedIcon fontSize="small" />}
        edgeTabIndex={1}
        edgeTabCount={3}
        paperSx={{ width: { xs: "min(100vw, 520px)", sm: 540, md: 560 } }}
      >
        <WarehousePreflightChecksPanel
          preflight={warehousePreflight}
          running={preflightRunning}
          error={preflightError}
          onRunChecks={() => {
            void runWarehousePreflightChecks({
              missionLoaded: missionLoadedForReadiness,
            });
          }}
        />
      </TaskPreflightCommandsDrawer>

      <TaskPreflightCommandsDrawer
        open={warehouseMissionDrawer.open}
        onOpenChange={handleWarehouseMissionOpenChange}
        title="Warehouse Fly"
        subtitle="Automated scan, product scan, and manual mapping"
        tabLabel="FLY"
        tabIcon={<ExploreRoundedIcon fontSize="small" />}
        edgeTabIndex={2}
        edgeTabCount={3}
        paperSx={{ width: { xs: "min(100vw, 520px)", sm: 540, md: 560 } }}
      >
        <WarehouseFlyDrawerContent
          flyMode={flyMode}
          setFlyMode={setFlyMode}
          preflightPassed={warehousePreflightPassed}
          missionStatusProps={{
            missionName,
            missionState,
            activeFlightId,
            lastError: missionStatus?.mission_lifecycle?.last_error,
          }}
          readinessProps={{
            readiness: warehouseFlightReadiness,
            preflight: warehousePreflight,
            loading: flightReadinessLoading,
            starting: startingScan,
            startDisabled: startScanDisabled,
            startDisabledReason: startScanTooltip,
            onStart: () => void handleStartWarehouseScan(),
            onPause: () => void handleFlightCommand("pause"),
            onAbort: () => void handleFlightCommand("abort"),
            onLand: () => void handleFlightCommand("land"),
            commandBusy: flightCommandBusy,
            showControls: missionState === "running",
          }}
          explorationProps={{
            embedded: true,
            warehouseMapId: selectedWarehouseMapId,
            selectedDockId,
            warehouseName: selectedWarehouseMapName ?? undefined,
            warehousePreflightPassed,
            getToken,
            onLaunch: handleExplorationLaunch,
            onError: handleExplorationError,
          }}
          productScanProps={{
            warehouseMapId: selectedWarehouseMapId,
            token: authToken,
            onError: addError,
            mapPlacement: warehouseMapPlacement.panelProps,
          }}
          manualMappingProps={{
            embedded: true,
            activeFlightId,
            missionStatus,
            wsConnected,
            droneConnected,
            warehouseMapId: selectedWarehouseMapId,
            sensorRigId: selectedSensorRigId,
            dockId: selectedDockId,
            warehousePreflightPassed,
            setPendingFlightId,
            onPreflightRun: handleManualMappingPreflightRun,
            onMessage: setScanLaunchMessage,
            onError: addError,
            onScanResultReady: handleScanResultReady,
          }}
        />
      </TaskPreflightCommandsDrawer>
      <WarehouseDeleteConfirmationDialog
        target={deleteTarget}
        busy={deletingWarehouseMap || deletingSensorRig || deletingScannedMap}
        onClose={() => setDeleteTarget(null)}
      />
    </>
  );
}
