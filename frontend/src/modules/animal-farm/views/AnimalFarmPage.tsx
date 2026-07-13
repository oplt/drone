import { useEffect, useRef, useState, useCallback, useMemo, useContext } from "react";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { useNotice } from "../../../shared/ui/NoticeContext";
import {
  Box,
  Paper,
  Stack,
  Typography,
  Divider,
  TextField,
  Alert,
  CircularProgress,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
} from "@mui/material";
import Header from "../../../shared/layout/WorkflowHeader";
import { Polyline, OverlayView } from "@react-google-maps/api";
import { getToken } from "../../session";
import DroneSvg from "../../../assets/Drone.svg?react";
import SvgIcon from "@mui/material/SvgIcon";
import RoomIcon from "@mui/icons-material/Room";
import {
  CesiumViewControls,
  DEFAULT_MISSION_MAP_ENGINE,
  GoogleMapsContext,
  MissionMapViewport,
  RouteDrawControls,
  TerraDrawController,
  useDroneCenter,
  useDroneMapFollow,
  useUserLocation,
  type CesiumViewMode,
  type MissionMapEngine,
  type RouteDrawMode,
  type RouteDrawToolMode,
  type TerraDrawEditorMode,
  type TerraDrawFeature,
} from "../../maps";
import { createFarmBorderDrawBridge } from "../../maps/utils/flatBoundaryDrawBridge";
import { ErrorAlerts } from "../../../shared/ui/ErrorAlerts";
import {
  MissionPreflightPanel,
  MissionStatusChips,
  MissionVideoPanel,
  useAutoStartVideo,
  useMissionCommandMetrics,
  useMissionWebsocketRuntime,
  startMissionWithPreflight,
  type PreflightRunResponse,
} from "../../mission-runtime";
import { MissionCommandPanel } from "../../mission-runtime/components/MissionCommandPanel";
import {
  MapEngineSelectionOverlay,
  MapShapeActionPopover,
  MissionSurveyCameraSection,
  TaskPreflightCommandsDrawer,
  useMapShapeActionPrompt,
  useTaskPreflightCommandsDrawer,
} from "../../mission-workflow";
import { useMissionAltitudeInput } from "../../mission-workflow/hooks/useMissionAltitudeInput";
import { stripClosedRing, useFields, FIELD_WORKFLOW_SCOPES, type LonLat } from "../../fields";
import { VideoAnalysisPanel } from "../../video-analysis";
import { useErrors } from "../../../shared/hooks/useErrors";
import { type LatLng } from "../../../shared/utils/extractLatLng";
import type { TerraDraw } from "terra-draw";
import {
  createLivestockTask,
  fetchHerds as loadHerds,
  fetchHerdLatestPositions,
  fetchHerdRiskAlerts,
  planLivestockTaskMission,
} from "../api/livestockApi";
import type { Herd, HerdAlert, HerdLatestPos } from "../types"; import { frontendLogger } from "../../../shared/logging";

type Waypoint = { lat: number; lon: number; alt: number };




interface MissionStatus {
  flight_id?: string;
  mission_name?: string;
  telemetry?: {
    running: boolean;
    active_connections?: number;
    has_position_data?: boolean;
    position?: {
      lat?: number;
      lon?: number;
      lng?: number;
      alt?: number;
      relative_alt?: number;
    };
  };
  orchestrator?: {
    drone_connected: boolean;
  };
}

const containerStyle = { width: "100%", height: "400px" };
const defaultCenter = { lat: 50.8503, lng: 4.3517 };

export default function AnimalFarmPage() {
  const { notify } = useNotice();
  const preflightCommandsDrawer = useTaskPreflightCommandsDrawer();
  const mapRef = useRef<google.maps.Map | null>(null);
  const terraDrawRef = useRef<TerraDraw | null>(null);

  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const [farmBorder, setFarmBorder] = useState<LonLat[] | null>(null);
  const [farmBorderName, setFarmBorderName] = useState("Pasture A");

  const [name, setName] = useState<string>("field-plan-1");
  const [sending, setSending] = useState(false);
  const [center, setCenter] = useState<LatLng>(defaultCenter);

  const { errors, addError, clearErrors, dismissError } = useErrors();
  const handleLocationError = useCallback((error: GeolocationPositionError) => {
    frontendLogger.error("frontend", "Error getting location", { message: error.message, code: error.code });
    const message = `Failed to get location: ${error.message}`;
    addError(message);
    return message;
  }, [addError]);
  const { userCenter, loadingLocation } = useUserLocation({
    onLocationError: handleLocationError,
  });
  const {
    alt,
    setAlt,
    altInput,
    setAltInput,
    handleAltitudeInputChange,
    normalizeAltitude,
  } = useMissionAltitudeInput({ initialAltitude: 30, addError });
  const { createField: createFarmBorderRecord, saving: savingFarmBorder } = useFields(
    FIELD_WORKFLOW_SCOPES.animalFarm,
  );

  const syncFarmBorderFromSnapshot = useCallback((snapshot: TerraDrawFeature[]) => {
    const boundary = [...snapshot]
      .reverse()
      .find((feature) => {
        if (!feature.id || !feature.geometry) return false;
        if (feature.geometry.type === "Polygon") return true;
        if (feature.geometry.type === "LineString") {
          const coords = feature.geometry.coordinates as [number, number][] | undefined;
          return Array.isArray(coords) && coords.length >= 3;
        }
        return false;
      });
    if (!boundary?.geometry) {
      setFarmBorder(null);
      return;
    }
    if (boundary.geometry.type === "Polygon") {
      const coords = (boundary.geometry.coordinates as [number, number][][])[0];
      setFarmBorder(coords.map(([lon, lat]) => [lon, lat] as LonLat));
      return;
    }
    const coords = boundary.geometry.coordinates as [number, number][];
    setFarmBorder(coords.map(([lon, lat]) => [lon, lat] as LonLat));
  }, []);

  const shapePrompt = useMapShapeActionPrompt({
    terraDrawRef,
    syncSnapshot: syncFarmBorderFromSnapshot,
  });
  const farmBorderDraw = useMemo(
    () =>
      createFarmBorderDrawBridge({
        setFarmBorder,
        onBoundaryDrawStarted: shapePrompt.notifyBoundaryDrawStarted,
      }),
    [shapePrompt.notifyBoundaryDrawStarted],
  );

  const [mapZoom, setMapZoom] = useState<number>(12);
  const [preflightRun, setPreflightRun] =
    useState<PreflightRunResponse | null>(null);

  const [manualStreamKey, setManualStreamKey] = useState(0);
  const [mapReady, setMapReady] = useState(false);
  const videoToken = getToken();
  const waypointMarkersRef = useRef<any[]>([]);
  const [useCesium, setUseCesium] = useState(false);
  const [mapEngine, setMapEngine] = useState<MissionMapEngine>(DEFAULT_MISSION_MAP_ENGINE);
  const [drawMode, setDrawMode] = useState<RouteDrawMode>("point");
  const [terraDrawMode, setTerraDrawMode] = useState<TerraDrawEditorMode>("point");
  const [, setTerraDrawReady] = useState(false);
  const [terraDrawFeatureCount, setTerraDrawFeatureCount] = useState(0);
  const [drawWaypointHistory, setDrawWaypointHistory] = useState<number[]>([]);
  const [cesiumViewMode, setCesiumViewMode] = useState<CesiumViewMode>("tilted");


  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY as string;
  const mapId = (import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string) || "";
  const API_BASE_RAW = import.meta.env.VITE_API_BASE_URL ?? "";
  const API_BASE_CLEAN = (API_BASE_RAW || "http://localhost:8000").replace(/\/$/, "");
  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoRetryCount, setVideoRetryCount] = useState(0);
  const {
    missionStatus,
    activeFlightId,
    setPendingFlightId,
    telemetry,
    wsConnected,
    droneConnected,
  } = useMissionWebsocketRuntime<MissionStatus>({
    apiBase: API_BASE_CLEAN,
    getTokenFn: getToken,
    onError: addError,
    alwaysConnect: true,
  });
  const droneCenter = useDroneCenter(telemetry);
  const { heading, armed } = useMissionCommandMetrics(telemetry);

  const handleRouteDrawComplete = useCallback(
    (result: {
      type: "point" | "polyline" | "polygon";
      coordinates: [number, number] | [number, number][];
    }) => {
      if (result.type === "polygon") {
        const ring = stripClosedRing(
          (result.coordinates as [number, number][]).map(([lon, lat]) => [lon, lat] as LonLat),
        );
        if (ring.length >= 3) {
          setFarmBorder(ring);
        }
        setDrawMode("none");
        return;
      }

      if (result.type === "polyline") {
        const coordinates = result.coordinates as [number, number][];
        setWaypoints(coordinates.map(([lon, lat]) => ({ lat, lon, alt })));
        setDrawWaypointHistory([coordinates.length]);
        setDrawMode("point");
        return;
      }

      if (result.type === "point") {
        const [lon, lat] = result.coordinates as [number, number];
        setWaypoints((prev) => [...prev, { lat, lon, alt }]);
        setDrawWaypointHistory((prev) => [...prev, 1]);
        return;
      }
    },
    [alt],
  );
  const handleRouteToolModeChange = useCallback(
    (toolMode: RouteDrawToolMode) => {
      shapePrompt.resetBoundaryDrawSession();
      if (mapEngine === "google") {
        const googleModeMap: Record<RouteDrawToolMode, TerraDrawEditorMode> = {
          none: "select",
          point: "point",
          polyline: "linestring",
          polygon: "polygon",
          rectangle: "rectangle",
          circle: "circle",
          triangle: "polygon",
        };
        setTerraDrawMode(googleModeMap[toolMode]);
        return;
      }
      const flatModeMap: Record<RouteDrawToolMode, RouteDrawMode> = {
        none: "none",
        point: "point",
        polyline: "polyline",
        polygon: "polygon",
        rectangle: "rectangle",
        circle: "circle",
        triangle: "triangle",
      };
      setDrawMode(flatModeMap[toolMode]);
    },
    [mapEngine, shapePrompt],
  );
  const syncRouteFromTerraDraw = useCallback(
    (snapshot: TerraDrawFeature[]) => {
      const next: Waypoint[] = [];
      setTerraDrawFeatureCount(snapshot.filter((feature) => feature.id != null).length);
      snapshot.forEach((feature) => {
        const geometry = feature.geometry;
        if (geometry?.type === "Point" && Array.isArray(geometry.coordinates)) {
          const [lon, lat] = geometry.coordinates as [number, number];
          if (Number.isFinite(lat) && Number.isFinite(lon)) next.push({ lat, lon, alt });
        }
        if (geometry?.type === "LineString" && Array.isArray(geometry.coordinates)) {
          (geometry.coordinates as [number, number][]).forEach(([lon, lat]) => {
            if (Number.isFinite(lat) && Number.isFinite(lon)) next.push({ lat, lon, alt });
          });
        }
      });
      setWaypoints(next);
    },
    [alt],
  );

  const handleTerraSnapshotChange = useCallback(
    (snapshot: TerraDrawFeature[]) => {
      syncRouteFromTerraDraw(snapshot);
      shapePrompt.handleSnapshotChange(snapshot);
    },
    [shapePrompt, syncRouteFromTerraDraw],
  );

  const handleFarmBorderSave = useCallback(async () => {
    if (!farmBorder || farmBorder.length < 3) {
      addError("Draw a farm border polygon (min 3 points) before saving.");
      return;
    }
    if (!farmBorderName.trim()) {
      addError("Please enter a border name.");
      return;
    }
    try {
      await createFarmBorderRecord({
        name: farmBorderName.trim(),
        coordinates: farmBorder,
      });
      shapePrompt.closePrompt();
    } catch (e: unknown) {
      addError(e instanceof Error ? e.message : "Failed to save farm border");
    }
  }, [addError, createFarmBorderRecord, farmBorder, farmBorderName, shapePrompt]);
  const handleMapEngineChange = useCallback((next: MissionMapEngine) => {
    setMapEngine(next);
    setUseCesium(next === "cesium");
  }, []);
  const droneReady = Boolean(droneConnected);
  const { startingVideo, streamKey: autoStreamKey } = useAutoStartVideo({
    apiBase: API_BASE_CLEAN,
    getToken,
    enabled: Boolean(activeFlightId && droneReady),
    onError: addError,
    resetKey: activeFlightId ?? "none",
  });
  const { isLoaded, loadError } = useContext(GoogleMapsContext);

  useEffect(() => {
    if (!droneConnected) {
      setManualStreamKey(0);
    }
  }, [droneConnected]);

  const streamKey = manualStreamKey || autoStreamKey;

const [herds, setHerds] = useState<Herd[]>([]);
const [selectedHerdId, setSelectedHerdId] = useState<number | null>(null);

const [latestPositions, setLatestPositions] = useState<HerdLatestPos[]>([]);
const [herdAlerts, setHerdAlerts] = useState<HerdAlert[]>([]);

const [loadingHerdOps, setLoadingHerdOps] = useState(false);
const [collarIdForSearch, setCollarIdForSearch] = useState<string>("");

  const onMapLoad = useCallback((map: google.maps.Map) => {
    mapRef.current = map;
    setMapReady(true);
  }, []);

  const onMapZoomChanged = useCallback(() => {
    if (!mapRef.current) return;
    const zoom = mapRef.current.getZoom();
    if (typeof zoom === "number" && Number.isFinite(zoom)) {
      setMapZoom(zoom);
    }
  }, []);



    const handleVideoError = useCallback(() => {
      setVideoError("Failed to load video stream");
      setVideoRetryCount(prev => prev + 1);
    }, []);

    // Add video load success handler
    const handleVideoLoad = useCallback(() => {
      setVideoError(null);
      setVideoRetryCount(0);
    }, []);

    const handleVideoRetry = useCallback(() => {
      setManualStreamKey(Date.now());
      setVideoError(null);
    }, []);

  // AdvancedMarkerElement for waypoint markers (avoids deprecated google.maps.Marker).
  useEffect(() => {
    if (!isLoaded || !mapReady) return;
    if (!mapRef.current) return;

    const markerLib = (google.maps as any)?.marker;
    if (!markerLib?.AdvancedMarkerElement) {
      // Marker library not available; skip rendering to avoid deprecation warnings.
      return;
    }

    waypointMarkersRef.current.forEach((marker) => {
      try {
        if (marker) {
          if ("map" in marker) marker.map = null;
          else if (typeof marker.setMap === "function") marker.setMap(null);
        }
      } catch {
        // ignore cleanup errors
      }
    });
    waypointMarkersRef.current = [];

    if (waypoints.length === 0) return;

    waypoints.forEach((p, idx) => {
      const content = document.createElement("div");
      content.style.width = "26px";
      content.style.height = "26px";
      content.style.borderRadius = "50%";
      content.style.background = "#fff";
      content.style.border = "2px solid #1976d2";
      content.style.color = "#1976d2";
      content.style.display = "flex";
      content.style.alignItems = "center";
      content.style.justifyContent = "center";
      content.style.fontSize = "12px";
      content.style.fontWeight = "600";
      content.style.boxShadow = "0 2px 6px rgba(0,0,0,0.2)";
      content.textContent = `${idx + 1}`;

      const marker = new markerLib.AdvancedMarkerElement({
        map: mapRef.current,
        position: { lat: p.lat, lng: p.lon },
        content,
        title: `Waypoint ${idx + 1}`,
      });

      waypointMarkersRef.current.push(marker);
    });

    return () => {
      waypointMarkersRef.current.forEach((marker) => {
        try {
          if (marker) {
            if ("map" in marker) marker.map = null;
            else if (typeof marker.setMap === "function") marker.setMap(null);
          }
        } catch {
          // ignore cleanup errors
        }
      });
      waypointMarkersRef.current = [];
    };
  }, [isLoaded, mapReady, waypoints]);

const fetchHerds = useCallback(async () => {
  const token = getToken();
  if (!token) return;

  const data = await loadHerds(token);
  setHerds(data);

  // Auto-select first herd if none selected
  if (!selectedHerdId && data.length > 0) setSelectedHerdId(data[0].id);
}, [API_BASE_CLEAN, selectedHerdId]);

const fetchLatestPositions = useCallback(async (herdId: number) => {
  const token = getToken();
  if (!token) return;

  setLatestPositions(await fetchHerdLatestPositions(herdId, token));
}, [API_BASE_CLEAN]);

const fetchRisk = useCallback(async (herdId: number) => {
  const token = getToken();
  if (!token) return;

  setHerdAlerts(await fetchHerdRiskAlerts(herdId, token));
}, [API_BASE_CLEAN]);



useEffect(() => {
  (async () => {
    try {
      await fetchHerds();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load herds";
      addError(msg);
    }
  })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);

useEffect(() => {
  if (!selectedHerdId) return;
  (async () => {
    try {
      setLoadingHerdOps(true);
      await Promise.all([
        fetchLatestPositions(selectedHerdId),
        fetchRisk(selectedHerdId),
      ]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load herd ops data";
      addError(msg);
    } finally {
      setLoadingHerdOps(false);
    }
  })();
}, [selectedHerdId, fetchLatestPositions, fetchRisk, addError]);
  // Cleanup on unmount (disconnect WS)
  useDroneMapFollow({
    mapRef,
    droneCenter,
    wsConnected,
    onInitialSnap: () => setMapZoom(18),
  });

  const onMapClick = useCallback(
    (e: google.maps.MapMouseEvent) => {
      if (mapEngine === "google" && terraDrawMode !== "static" && terraDrawMode !== "select") return;
      if (drawMode === "none") return;
      if (!e.latLng) return;
      const lat = e.latLng.lat();
      const lng = e.latLng.lng();
      setWaypoints((prev) => [...prev, { lat, lon: lng, alt }]);
    },
    [alt, drawMode, mapEngine, terraDrawMode],
  );

  const undo = () => {
    if (mapEngine === "google" && terraDrawRef.current) {
      shapePrompt.deleteSelectedDrawing(syncRouteFromTerraDraw);
      return;
    }
    setWaypoints((prev) => {
      const removeCount = drawWaypointHistory.at(-1) ?? 1;
      return prev.slice(0, Math.max(0, prev.length - removeCount));
    });
    setDrawWaypointHistory((prev) => prev.slice(0, -1));
  };
  const clear = () => {
    setWaypoints([]);
    setDrawWaypointHistory([]);
  };



    const sendMission = async () => {
      const token = getToken();
      if (!token) {
        addError("Not authenticated");
        return;
      }

      if (waypoints.length < 2) {
        addError("Select at least 2 waypoints");
        return;
      }

      if (!name.trim()) {
        addError("Please enter a field plan name");
        return;
      }

      const altToUse = altInput === "" ? NaN : Number(altInput);
      if (!Number.isFinite(altToUse) || altToUse < 1 || altToUse > 500) {
        addError("Altitude must be between 1 and 500 meters");
        return;
      }

      setSending(true);
      clearErrors();

      try {
        const payload = {
          name: name.trim(),
          cruise_alt: altToUse,
          waypoints: waypoints.map((wp) => ({
            lat: wp.lat,
            lon: wp.lon,
            alt: wp.alt,
          })),
        };
        const { preflight, mission: data } = await startMissionWithPreflight(payload, token);
        setPreflightRun(preflight);
        notify(`Flight plan "${data.mission_name}" started. Tracking flight.`, "success");

        setPendingFlightId(data.flight_id ?? null);

        // Clear waypoints after successful mission start
        setWaypoints([]);
        setAlt(altToUse);
        setAltInput(String(altToUse));

      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Error creating flight plan";
        addError(message);
      } finally {
        setSending(false);
      }
    };

const createTaskAndPlan = useCallback(async (type: "census" | "herd_sweep" | "search_locate") => {
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

    const params: any = {};
    if (type === "search_locate" && collarIdForSearch.trim()) {
      params.collar_id = collarIdForSearch.trim();
    }

    // 1) Create task
    const task = await createLivestockTask(selectedHerdId, type, params, token);
    const plan = await planLivestockTaskMission(task.id, token);

    const m = plan?.mission;
    const wps = (m?.waypoints ?? []).map((wp: any) => ({
      lat: wp.lat,
      lon: wp.lon,
      alt: wp.alt ?? alt,
    }));

    if (wps.length === 0) {
      addError("Mission plan returned no waypoints");
      return;
    }

    // Fill in existing mission builder state
    setWaypoints(wps);
    setName(`herd-${selectedHerdId}-${type}-${Date.now()}`);

    // Optional: center map to first waypoint
    setCenter({ lat: wps[0].lat, lng: wps[0].lon });

  } catch (e) {
    addError(e instanceof Error ? e.message : "Task planning error");
  } finally {
    setLoadingHerdOps(false);
  }
}, [API_BASE_CLEAN, selectedHerdId, collarIdForSearch, alt, addError, clearErrors]);



  const polylinePath = useMemo(
    () => waypoints.map((p) => ({ lat: p.lat, lng: p.lon })),
    [waypoints],
  );

  // If drone exists, keep map centered near it initially
  const mapCenter = useMemo(() => {
    if (droneCenter) {
      return droneCenter;
    }
    if (waypoints.length > 0) {
      return { lat: waypoints[0].lat, lng: waypoints[0].lon };
    }
    return userCenter || center;
  }, [droneCenter, waypoints, userCenter, center]);

  const mapOptions = useMemo(
    () => ({
      streetViewControl: false,
      mapTypeControl: false,
      fullscreenControl: true,
      clickableIcons: false,
      keyboardShortcuts: false,
      gestureHandling: "greedy" as const,
      maxZoom: 20,
      minZoom: 3,
      ...(mapId ? { mapId } : {}),
    }),
    [mapId],
  );

  return (
    <>
      <Header />
      <Paper sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Typography variant="h6">Animal Farms</Typography>

          <FormControl size="small" fullWidth>
            <InputLabel id="herd-select-label">Herd</InputLabel>
            <Select
              labelId="herd-select-label"
              label="Herd"
              value={selectedHerdId ?? ""}
              onChange={(e) => setSelectedHerdId(Number(e.target.value))}
            >
              {herds.map((h) => (
                <MenuItem key={h.id} value={h.id}>{h.name}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <Stack direction="row" spacing={0.25} flexWrap="wrap" useFlexGap>
            <ActionIconButton
              variant="plan"
              title="Plan Census"
              color="primary"
              loading={loadingHerdOps}
              disabled={!selectedHerdId}
              onClick={() => createTaskAndPlan("census")}
            />
            <ActionIconButton
              variant="plan"
              title="Plan Herd Sweep"
              color="primary"
              loading={loadingHerdOps}
              disabled={!selectedHerdId}
              onClick={() => createTaskAndPlan("herd_sweep")}
            />
          </Stack>

          <Stack direction="row" spacing={1}>
            <TextField variant="filled"
              size="small"
              label="Collar ID (optional)"
              value={collarIdForSearch}
              onChange={(e) => setCollarIdForSearch(e.target.value)}
              fullWidth
            />
            <ActionIconButton
              variant="search"
              title="Search"
              loading={loadingHerdOps}
              disabled={!selectedHerdId}
              onClick={() => createTaskAndPlan("search_locate")}
            />
          </Stack>

          <Divider />

          <Stack direction="row" spacing={0.25} alignItems="center">
            <ActionIconButton
              variant="refresh"
              title="Refresh positions"
              disabled={!selectedHerdId}
              onClick={() => selectedHerdId && fetchLatestPositions(selectedHerdId)}
            />
            <ActionIconButton
              variant="refresh"
              title="Refresh risk"
              disabled={!selectedHerdId}
              onClick={() => selectedHerdId && fetchRisk(selectedHerdId)}
            />
            {loadingHerdOps && <CircularProgress size={16} />}
          </Stack>

          {herdAlerts.slice(0, 4).map((a, idx) => (
            <Alert key={idx} severity={a.severity === "high" ? "error" : a.severity === "medium" ? "warning" : "info"}>
              {a.type}: {a.message} ({a.collar_id})
            </Alert>
          ))}
        </Stack>
      </Paper>

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
          spacing={2}
        >
          <Box>
            <Typography variant="h3">Field Operations</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Configure field routes, stream telemetry, and monitor imagery in real time.
            </Typography>
          </Box>
          <MissionStatusChips droneConnected={droneConnected} wsConnected={wsConnected} />
        </Stack>

        <ErrorAlerts
          errors={errors}
          onDismiss={dismissError}
          onClearAll={clearErrors}
        />

        {!apiKey ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Missing Google Maps API Key. Please set VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY
            in your .env file.
          </Alert>
        ) : loadError ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load Google Maps. {loadError.message}
            {" "}
            Ensure the Maps JavaScript API is enabled, billing is active, and the
            key allows your domain (for local dev: http://localhost:5173/*).
          </Alert>
        ) : !mapId ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Google Maps Map ID is not set. Advanced markers require a Map ID. Set
            VITE_GOOGLE_MAPS_MAP_ID to remove this warning.
          </Alert>
        ) : (
          <>
            <Box sx={{ mb: 3 }}>
              <MissionSurveyCameraSection
                setupSubtitle="Field plan, altitude, and route waypoints"
                video={
                  <MissionVideoPanel
                    embedded
                    title="Survey Camera"
                    imgAlt="Survey camera stream"
                    disconnectedMessage="Connect the drone to view the survey stream."
                    frameHeight={360}
                    apiBase={API_BASE_CLEAN}
                    streamKey={streamKey}
                    videoToken={videoToken}
                    startingVideo={startingVideo}
                    videoError={videoError}
                    videoRetryCount={videoRetryCount}
                    droneConnected={droneConnected}
                    telemetry={telemetry}
                    onVideoError={handleVideoError}
                    onVideoLoad={handleVideoLoad}
                    onRetry={handleVideoRetry}
                  />
                }
                map={
                  <Box
                    sx={{
                      borderRadius: 2,
                      overflow: "hidden",
                      border: "1px solid",
                      borderColor: "divider",
                      backgroundColor: "background.paper",
                    }}
                  >
                    <TerraDrawController
                      map={mapReady && mapEngine === "google" ? mapRef.current : null}
                      enabled={mapEngine === "google"}
                      mode={terraDrawMode}
                      drawRef={terraDrawRef}
                      onReadyChange={setTerraDrawReady}
                      onSnapshotChange={handleTerraSnapshotChange}
                      onChangeEvent={shapePrompt.handleChangeEvent}
                      onSelectionChange={shapePrompt.handleSelectionChange}
                      onError={addError}
                    />
                    <MissionMapViewport
                      loadingLocation={loadingLocation}
                      isLoaded={isLoaded}
                      useCesium={useCesium}
                      mapEngine={mapEngine}
                      googleMapProps={{
                        mapContainerStyle: containerStyle,
                        center: mapCenter,
                        zoom: mapZoom,
                        onClick: onMapClick,
                        onLoad: onMapLoad,
                        onZoomChanged: onMapZoomChanged,
                        options: mapOptions,
                      }}
                      cesiumMapProps={{
                        center: mapCenter,
                        zoom: mapZoom,
                        viewMode: cesiumViewMode,
                        waypoints,
                        fieldBoundary: farmBorder && farmBorder.length >= 3 ? farmBorder : null,
                        droneCenter,
                        headingDeg: typeof heading === "number" ? heading : null,
                        drawMode,
                        onDrawComplete: handleRouteDrawComplete,
                        onBoundaryDrawStarted: farmBorderDraw.onBoundaryDrawStarted,
                        onBoundaryDrawProgress: farmBorderDraw.onBoundaryDrawProgress,
                      }}
                      leafletMapProps={{
                        center: mapCenter,
                        zoom: mapZoom,
                        waypoints,
                        droneCenter,
                        userCenter,
                        drawMode,
                        onDrawComplete: handleRouteDrawComplete,
                        onBoundaryDrawStarted: farmBorderDraw.onBoundaryDrawStarted,
                        onBoundaryDrawProgress: farmBorderDraw.onBoundaryDrawProgress,
                        height: 400,
                      }}
                      mapLibreMapProps={{
                        center: mapCenter,
                        zoom: mapZoom,
                        waypoints,
                        droneCenter,
                        userCenter,
                        drawMode,
                        onDrawComplete: handleRouteDrawComplete,
                        onBoundaryDrawStarted: farmBorderDraw.onBoundaryDrawStarted,
                        onBoundaryDrawProgress: farmBorderDraw.onBoundaryDrawProgress,
                        height: 400,
                      }}
                      googleWrapperSx={{ position: "relative" }}
                      googleOverlay={
                        <>
                          <MapShapeActionPopover
                            open={shapePrompt.open}
                            variant="farm-border"
                            name={farmBorderName}
                            saving={savingFarmBorder}
                            onNameChange={setFarmBorderName}
                            onSave={handleFarmBorderSave}
                            onDismiss={shapePrompt.closePrompt}
                          />
                          <RouteDrawControls
                            mode={drawMode}
                            activeToolMode={
                              mapEngine === "google"
                                ? terraDrawMode === "linestring"
                                  ? "polyline"
                                  : terraDrawMode === "select" || terraDrawMode === "static"
                                    ? "none"
                                    : terraDrawMode === "freehand"
                                      ? "polygon"
                                      : terraDrawMode
                                : undefined
                            }
                            onModeChange={setDrawMode}
                            onToolModeChange={handleRouteToolModeChange}
                            onUndo={undo}
                            hasWaypoints={waypoints.length > 0 || terraDrawFeatureCount > 0}
                          />
                          <MapEngineSelectionOverlay>
                            <CesiumViewControls
                              useCesium={useCesium}
                              onUseCesiumChange={(next: boolean) =>
                                handleMapEngineChange(
                                  next ? "cesium" : DEFAULT_MISSION_MAP_ENGINE,
                                )
                              }
                              mapEngine={mapEngine}
                              onMapEngineChange={handleMapEngineChange}
                              viewMode={cesiumViewMode}
                              onViewModeChange={setCesiumViewMode}
                            />
                          </MapEngineSelectionOverlay>
                        </>
                      }
                      googleChildren={
                        <>
                          {droneCenter && (
                            <OverlayView
                              position={droneCenter}
                              mapPaneName={OverlayView.OVERLAY_LAYER}
                            >
                              <div
                                style={{
                                  transform: `translate(-50%, -50%) rotate(${
                                    typeof heading === "number" ? heading : 0
                                  }deg)`,
                                  transformOrigin: "center",
                                  color: armed ? "#1976d2" : "#9aa0a6",
                                  zIndex: 9999,
                                }}
                              >
                                <SvgIcon
                                  component={DroneSvg}
                                  inheritViewBox
                                  sx={{
                                    width: 40,
                                    height: 40,
                                    filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.35))",
                                  }}
                                />
                                {activeFlightId && (
                                  <div
                                    style={{
                                      position: "absolute",
                                      top: "-28px",
                                      left: "50%",
                                      transform: "translateX(-50%)",
                                      background: "white",
                                      padding: "2px 6px",
                                      borderRadius: "3px",
                                      fontSize: "10px",
                                      whiteSpace: "nowrap",
                                      boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
                                    }}
                                  >
                                    Flight: {activeFlightId.substring(0, 8)}...
                                  </div>
                                )}
                              </div>
                            </OverlayView>
                          )}

                          {userCenter && (
                            <OverlayView
                              position={userCenter}
                              mapPaneName={OverlayView.OVERLAY_LAYER}
                            >
                              <div
                                style={{
                                  transform: "translate(-50%, -50%)",
                                  color: "#4caf50",
                                }}
                              >
                                <RoomIcon fontSize="large" />
                              </div>
                            </OverlayView>
                          )}

                          {waypoints.length >= 2 && (
                            <Polyline
                              path={polylinePath}
                              options={{
                                strokeColor: "#1976d2",
                                strokeOpacity: 0.8,
                                strokeWeight: 3,
                              }}
                            />
                          )}

                          {latestPositions.map((p) => (
                            <OverlayView
                              key={p.animal_id}
                              position={{ lat: p.lat, lng: p.lon }}
                              mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}
                            >
                              <Box
                                sx={{
                                  transform: "translate(-50%, -100%)",
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 0.5,
                                  background: "rgba(0,0,0,0.55)",
                                  color: "white",
                                  px: 1,
                                  py: 0.25,
                                  borderRadius: 1,
                                  fontSize: 12,
                                }}
                              >
                                <RoomIcon fontSize="small" />
                                <span>{p.animal_name || p.collar_id}</span>
                              </Box>
                            </OverlayView>
                          ))}
                        </>
                      }
                    />
                  </Box>
                }
                setup={
                  <Stack spacing={2}>
                    <Typography variant="body2" color="text.secondary">
                      Click on the map to add waypoints. Markers are ordered (1..N).
                    </Typography>

                    <TextField
                      variant="filled"
                      label="Field plan name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      size="small"
                      fullWidth
                      required
                      error={!name.trim()}
                      helperText={!name.trim() ? "Field plan name is required" : ""}
                    />

                    <TextField
                      variant="filled"
                      label="Cruise altitude (m)"
                      type="text"
                      value={altInput}
                      onChange={(e) => handleAltitudeInputChange(e.target.value)}
                      onBlur={normalizeAltitude}
                      size="small"
                      fullWidth
                      inputProps={{ inputMode: "numeric", pattern: "\\d*" }}
                      error={altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)}
                      helperText={
                        altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)
                          ? "Must be between 1–500m"
                          : ""
                      }
                    />

                    <Typography variant="subtitle2">Waypoints: {waypoints.length}</Typography>

                    <Stack direction="row" spacing={0.25}>
                      <ActionIconButton
                        variant="undo"
                        title="Undo Last"
                        disabled={waypoints.length === 0 || sending}
                        onClick={undo}
                      />
                      <ActionIconButton
                        variant="delete"
                        title="Clear All"
                        color="error"
                        disabled={waypoints.length === 0 || sending}
                        onClick={clear}
                      />
                    </Stack>

                    <Stack direction="row" justifyContent="flex-end">
                      <ActionIconButton
                        variant="play"
                        title={sending ? "Sending…" : "Start Flight Plan"}
                        color="primary"
                        size="medium"
                        loading={sending}
                        disabled={
                          sending ||
                          waypoints.length < 2 ||
                          !name.trim() ||
                          altInput === "" ||
                          Number(altInput) < 1 ||
                          Number(altInput) > 500
                        }
                        onClick={sendMission}
                      />
                    </Stack>

                    {activeFlightId && (
                      <Alert severity="info">
                        Active flight: {missionStatus?.mission_name || "Loading..."}
                      </Alert>
                    )}
                  </Stack>
                }
                videoAnalysis={
                  <VideoAnalysisPanel
                    embedded
                    missionId={activeFlightId}
                    flightActive={Boolean(activeFlightId)}
                  />
                }
              />
            </Box>

            <Divider sx={{ mb: 2 }} />

            {/* Display waypoints list */}
            {waypoints.length > 0 && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" sx={{ mb: 1 }}>
                  Waypoints
                </Typography>
                <Stack spacing={1}>
                  {waypoints.map((wp, idx) => (
                    <Typography key={idx} variant="body2">
                      {idx + 1}. Lat: {wp.lat.toFixed(6)}, Lon: {wp.lon.toFixed(6)}, Alt:{" "}
                      {wp.alt ?? alt}m
                    </Typography>
                  ))}
                </Stack>
              </Box>
            )}

            {/* Status display panel */}
            {missionStatus && (activeFlightId || waypoints.length > 0) && (
              <Box sx={{ mt: 2, p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: "bold", mb: 1 }}>
                  Flight Status
                </Typography>
                <Stack spacing={0.5}>
                  {missionStatus.flight_id && (
                    <Typography variant="caption" component="div">
                      Flight ID: {missionStatus.flight_id}
                    </Typography>
                  )}
                  {missionStatus.mission_name && (
                    <Typography variant="caption" component="div">
                      Plan: {missionStatus.mission_name}
                    </Typography>
                  )}
                  <Typography variant="caption" component="div">
                    Telemetry:{" "}
                    {missionStatus.telemetry?.running ? (
                      <span style={{ color: "green" }}>Running</span>
                    ) : (
                      <span style={{ color: "red" }}>Stopped</span>
                    )}
                  </Typography>
                  {missionStatus.telemetry?.active_connections !== undefined && (
                    <Typography variant="caption" component="div">
                      WS Connections: {missionStatus.telemetry.active_connections}
                    </Typography>
                  )}
                  <Typography variant="caption" component="div">
                    Drone Connected:{" "}
                    {missionStatus.orchestrator?.drone_connected ? (
                      <span style={{ color: "green" }}>Yes</span>
                    ) : (
                      <span style={{ color: "red" }}>No</span>
                    )}
                  </Typography>
                </Stack>
              </Box>
            )}
          </>
        )}
      </Paper>

      <TaskPreflightCommandsDrawer
        open={preflightCommandsDrawer.open}
        onOpenChange={preflightCommandsDrawer.onOpenChange}
      >
        <MissionPreflightPanel
          apiBase={API_BASE_CLEAN}
          missionType="route"
          preflightRun={preflightRun}
          telemetry={telemetry}
        />
        <MissionCommandPanel
          telemetry={telemetry}
          droneConnected={droneConnected}
          missionStatus={missionStatus}
          activeFlightId={activeFlightId}
          apiBase={API_BASE_CLEAN}
        />
      </TaskPreflightCommandsDrawer>
    </>
  );
}
