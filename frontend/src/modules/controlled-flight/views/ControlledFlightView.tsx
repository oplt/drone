import { useEffect, useRef, useState, useCallback, useMemo, useContext } from "react";
import {
  Box,
  Button,
  Paper,
  Stack,
  Typography,
  TextField,
  Alert,
  CircularProgress,
  Chip,
} from "@mui/material";
import Header from "../../../shared/layout/WorkflowHeader";
import SvgIcon from "@mui/material/SvgIcon";
import DroneSvg from "../../../assets/Drone.svg?react";
import RoomIcon from "@mui/icons-material/Room";
import { GoogleMapsContext } from "../../../modules/maps/providers/googleMaps";
import { OverlayView, Polyline } from "@react-google-maps/api";
import { getToken } from "../../../modules/session";
import { ErrorAlerts } from "../../../shared/ui/ErrorAlerts";
import { MissionCommandPanel } from "../../../modules/mission-runtime";
import { MissionPreflightPanel } from "../../../modules/mission-runtime";
import { TaskControlFrame } from "../../../modules/mission-workflow";
import { MissionVideoPanel } from "../../../modules/mission-runtime";
import { MissionStatusChips } from "../../../modules/mission-runtime";
import { MissionMapViewport } from "../../../modules/maps";
import {
  RouteDrawControls,
  type RouteDrawMode,
  type RouteDrawToolMode,
} from "../../../modules/maps";
import { TerraDrawController, type TerraDrawEditorMode } from "../../../modules/maps";
import { useDroneCenter } from "../../../modules/maps";
import { useDroneMapFollow } from "../../../modules/maps";
import { useErrors } from "../../../shared/hooks/useErrors";
import { useAutoStartVideo } from "../../../modules/mission-runtime";
import { useMissionCommandMetrics } from "../../../modules/mission-runtime";
import { useMissionWebsocketRuntime } from "../../../modules/mission-runtime";
import type { LatLng } from "../../../shared/utils/extractLatLng";
import {
  startMissionWithPreflight,
  type PreflightRunResponse,
} from "../../mission-runtime";
import type { TerraDraw } from "terra-draw";
import { connectDroneTelemetry } from "../../mission-runtime/api/telemetryConnectApi";
import { useControlledPreflight } from "../hooks/useControlledPreflight";
import { useManualFlightControls } from "../hooks/useManualFlightControls";
import { MANUAL_CONTROL_BUTTONS } from "../types";

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

const readNestedValue = (value: unknown, path: string[]): unknown => {
  let current: unknown = value;
  for (const segment of path) {
    if (
        current == null ||
        typeof current !== "object" ||
        !(segment in (current as Record<string, unknown>))
    ) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
};

const firstFiniteNumber = (...values: unknown[]): number | null => {
  for (const value of values) {
    const num = Number(value);
    if (Number.isFinite(num)) return num;
  }
  return null;
};

export function ControlledFlightView() {
  const [controlFrameExpanded, setControlFrameExpanded] = useState(true);
  const containerStyle = { width: "100%", height: "400px" };
  const defaultCenter = { lat: 50.8503, lng: 4.3517 };

  const [alt, setAlt] = useState(30);
  const [altInput, setAltInput] = useState("30");
  const [name, setName] = useState("Controlled Flight");

  const mapRef = useRef<google.maps.Map | null>(null);
  const missionLaunchInFlightRef = useRef(false);
  const [userCenter, setUserCenter] = useState<LatLng | null>(null);
  const [sending, setSending] = useState(false);
  const [preflightRun, setPreflightRun] =
      useState<PreflightRunResponse | null>(null);

  const [center, setCenter] = useState(defaultCenter);
  const [loadingLocation, setLoadingLocation] = useState(true);
  const { errors, addError, clearErrors, dismissError } = useErrors();
  const [mapZoom, setMapZoom] = useState(12);
  const [drawMode, setDrawMode] = useState<RouteDrawMode>("point");
  const terraDrawRef = useRef<TerraDraw | null>(null);
  const [terraDrawMode, setTerraDrawMode] = useState<TerraDrawEditorMode>("point");
  const [, setTerraDrawReady] = useState(false);
  const [drawnPoints, setDrawnPoints] = useState<LatLng[]>([]);
  const [lastMissionId, setLastMissionId] = useState<string | null>(null);
  const [streamKey, setStreamKey] = useState(Date.now());
  const [mapReady, setMapReady] = useState(false);
  const videoToken = getToken();

  const API_BASE_CLEAN = ((import.meta.env.VITE_API_BASE_URL ?? "") || "http://localhost:8000").replace(
      /\/$/,
      ""
  );
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY as string;
  const mapId = (import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string) || "";

  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoRetryCount, setVideoRetryCount] = useState(0);
  const [droneManualConnected, setDroneManualConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const {
    missionStatus,
    activeFlightId,
    setPendingFlightId,
    telemetry,
    wsConnected,
    disconnect,
    droneConnected,
  } = useMissionWebsocketRuntime<MissionStatus>({
    apiBase: API_BASE_CLEAN,
    getTokenFn: getToken,
    onError: addError,
    alwaysConnect: droneManualConnected,
  });

  const trackedMissionId = activeFlightId ?? lastMissionId;
  const droneCenter = useDroneCenter(telemetry);
  const { heading, armed } = useMissionCommandMetrics(telemetry);

  const batteryPercent = useMemo(
      () =>
          firstFiniteNumber(
              readNestedValue(telemetry, ["battery", "remaining_percent"]),
              readNestedValue(telemetry, ["battery", "remaining"]),
              readNestedValue(telemetry, ["status", "battery_remaining"]),
              readNestedValue(telemetry, ["battery_remaining"])
          ),
      [telemetry]
  );

  const gpsFixType = useMemo(
      () =>
          firstFiniteNumber(
              readNestedValue(telemetry, ["gps", "fix_type"]),
              readNestedValue(telemetry, ["status", "gps_fix_type"]),
              readNestedValue(telemetry, ["gps_fix_type"])
          ),
      [telemetry]
  );

  const heartbeatReceived = useMemo(
      () => readNestedValue(telemetry, ["heartbeat", "last_received"]) != null,
      [telemetry]
  );

  const ekfOk = useMemo(() => {
    const v = readNestedValue(telemetry, ["ekf", "ok"]);
    return v == null ? null : Boolean(v);
  }, [telemetry]);

  const compassHealthy = useMemo(() => {
    const v = readNestedValue(telemetry, ["compass", "healthy"]);
    return v == null ? null : Boolean(v);
  }, [telemetry]);

  const connectDrone = useCallback(async () => {
    const token = getToken();
    if (!token) { addError("Not authenticated"); return; }
    setConnecting(true);
    try {
      await connectDroneTelemetry(token);
      setDroneManualConnected(true);
    } catch (e: unknown) {
      addError(e instanceof Error ? e.message : "Connect failed");
    } finally {
      setConnecting(false);
    }
  }, [API_BASE_CLEAN, addError]);

  const stopAllManualRef = useRef<() => void>(() => {});

  const {
    controlledPreflight,
    manualControlEnabled,
    setManualControlEnabled,
    runControlledPreflightCheck,
  } = useControlledPreflight({
    droneConnected,
    wsConnected,
    missionStatus,
    droneCenter,
    heartbeatReceived,
    gpsFixType,
    ekfOk,
    compassHealthy,
    batteryPercent,
    telemetry,
    onFailed: () => {
      setManualControlEnabled(false);
      stopAllManualRef.current();
    },
  });

  const manualControlReady = Boolean(
    controlledPreflight?.passed && droneManualConnected && (droneConnected || wsConnected),
  );

  const {
    activeManualCommands,
    manualControlError,
    lastManualCommand,
    beginManualControl,
    endManualControl,
    stopAllManualCommands,
    setManualControlError,
  } = useManualFlightControls({
    flightId: trackedMissionId,
    enabled: manualControlEnabled,
    ready: manualControlReady,
    onDisable: () => setManualControlEnabled(false),
  });

  stopAllManualRef.current = stopAllManualCommands;

  const droneReady = Boolean(droneManualConnected && (wsConnected || droneConnected) && droneCenter);
  const { startingVideo, streamKey: autoStreamKey } = useAutoStartVideo({
    apiBase: API_BASE_CLEAN,
    getToken,
    enabled: droneReady,
    onError: addError,
    resetKey: activeFlightId ?? "none",
  });

  const { isLoaded, loadError } = useContext(GoogleMapsContext);

  useEffect(() => {
    if (autoStreamKey) setStreamKey(autoStreamKey);
  }, [autoStreamKey]);

  const onMapLoad = useCallback((map: google.maps.Map) => {
    mapRef.current = map;
    setMapReady(true);
  }, []);

  const onMapUnmount = useCallback(() => {
    mapRef.current = null;
    setMapReady(false);
  }, []);

  const onMapZoomChanged = useCallback(() => {
    if (!mapRef.current) return;
    const zoom = mapRef.current.getZoom();
    if (typeof zoom === "number" && Number.isFinite(zoom)) {
      setMapZoom(zoom);
    }
  }, []);

  const lastSyncedCenterRef = useRef<LatLng | null>(null);
  const onMapCenterChanged = useCallback(() => {
    if (!mapRef.current) return;
    const c = mapRef.current.getCenter();
    if (!c) return;
    const newCenter = { lat: c.lat(), lng: c.lng() };
    const last = lastSyncedCenterRef.current;
    const hasChanged = !last ||
        Math.abs(last.lat - newCenter.lat) > 0.00001 ||
        Math.abs(last.lng - newCenter.lng) > 0.00001;
    if (hasChanged) {
      lastSyncedCenterRef.current = newCenter;
      setCenter(newCenter);
    }
  }, []);

  const onMapClick = useCallback(
      (e: google.maps.MapMouseEvent) => {
        if (terraDrawMode !== "static" && terraDrawMode !== "select") return;
        if (drawMode === "none" || !e.latLng) return;
        setDrawnPoints((prev) => [...prev, { lat: e.latLng!.lat(), lng: e.latLng!.lng() }]);
      },
      [drawMode, terraDrawMode]
  );
  const handleRouteToolModeChange = useCallback((toolMode: RouteDrawToolMode) => {
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
  }, []);

  useEffect(() => {
    if (!navigator.geolocation) {
      setLoadingLocation(false);
      return;
    }
    navigator.geolocation.getCurrentPosition(
        (position) => {
          const userLocation = {
            lat: position.coords.latitude,
            lng: position.coords.longitude,
          };
          setUserCenter(userLocation);
          setCenter(userLocation);
          setLoadingLocation(false);
        },
        (error) => {
          addError(`Failed to get location: ${error.message}`);
          setLoadingLocation(false);
        },
        { enableHighAccuracy: true, timeout: 5000, maximumAge: 0 }
    );
  }, [addError]);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  useDroneMapFollow({
    mapRef,
    droneCenter,
    wsConnected,
    onInitialSnap: () => setMapZoom(18),
  });

  const handleVideoError = useCallback(() => {
    setVideoError("Failed to load video stream");
    setVideoRetryCount((prev) => prev + 1);
    setTimeout(() => {
      setStreamKey(Date.now());
      setVideoError(null);
    }, 5000);
  }, []);

  const handleVideoLoad = useCallback(() => {
    setVideoError(null);
    setVideoRetryCount(0);
  }, []);

  // ── Mission launch ──

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

    missionLaunchInFlightRef.current = true;
    setSending(true);
    clearErrors();

    try {
      const payload: Record<string, unknown> = {
        name: name.trim(),
        cruise_alt: altToUse,
        mission_type: "controlled",
      };

      const { preflight, mission: data } = await startMissionWithPreflight(payload, token);
      setPreflightRun(preflight);

      setPendingFlightId(data.flight_id ?? null);
      setLastMissionId(data.flight_id ?? null);
      setAlt(altToUse);
      setAltInput(String(altToUse));
    } catch (err: unknown) {
      const message =
          err instanceof Error ? err.message : "Error creating flight session";
      addError(message);
    } finally {
      setSending(false);
      missionLaunchInFlightRef.current = false;
    }
  };

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

  const mapCenter = useMemo(() => userCenter || center, [userCenter, center]);
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
      [mapId]
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
              spacing={2}
          >
            <div>
              <Typography variant="h5">Controlled Flight Operations</Typography>
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                Connect to the drone, run preflight checks, and fly manually with
                keyboard or on-screen controls.
              </Typography>
            </div>
            <MissionStatusChips droneConnected={droneConnected} wsConnected={wsConnected} />
          </Stack>

          <ErrorAlerts
              errors={errors}
              onDismiss={dismissError}
              onClearAll={clearErrors}
          />

          {!apiKey ? (
              <Alert severity="error" sx={{ mb: 2 }}>
                Missing Google Maps API Key. Set VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY in your .env file.
              </Alert>
          ) : loadError ? (
              <Alert severity="error" sx={{ mb: 2 }}>
                Failed to load Google Maps. {loadError.message}
              </Alert>
          ) : (
              <Stack direction={{ xs: "column", md: "row" }} spacing={3} sx={{ mb: 3 }}>
                {/* Left column: video + map */}
                <Stack sx={{ flex: 1, minHeight: 200 }} spacing={2}>
                  <MissionVideoPanel
                      title="Flight Camera"
                      imgAlt="Pilot camera stream"
                      disconnectedMessage="Connect the drone to view the live camera stream."
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
                      onRetry={() => {
                        setStreamKey(Date.now());
                        setVideoError(null);
                      }}
                  />
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
                        map={mapReady ? mapRef.current : null}
                        enabled
                        mode={terraDrawMode}
                        drawRef={terraDrawRef}
                        onReadyChange={setTerraDrawReady}
                        onSnapshotChange={() => {}}
                        onError={addError}
                    />
                    <MissionMapViewport
                        loadingLocation={loadingLocation}
                        isLoaded={isLoaded}
                        useCesium={false}
                        googleMapProps={{
                          mapContainerStyle: containerStyle,
                          center: mapCenter,
                          zoom: mapZoom,
                          onClick: onMapClick,
                          onLoad: onMapLoad,
                          onUnmount: onMapUnmount,
                          onZoomChanged: onMapZoomChanged,
                          onCenterChanged: onMapCenterChanged,
                          options: mapOptions,
                        }}
                        googleWrapperSx={{ position: "relative" }}
                        googleOverlay={
                          <RouteDrawControls
                              mode={drawMode}
                              activeToolMode={
                                  terraDrawMode === "linestring"
                                      ? "polyline"
                                      : terraDrawMode === "select" || terraDrawMode === "static"
                                          ? "none"
                                          : terraDrawMode === "freehand"
                                            ? "polygon"
                                            : terraDrawMode
                              }
                              onModeChange={setDrawMode}
                              onToolModeChange={handleRouteToolModeChange}
                              onUndo={() => setDrawnPoints((prev) => prev.slice(0, -1))}
                              hasWaypoints={drawnPoints.length > 0}
                          />
                        }
                        cesiumMapProps={undefined}
                        googleChildren={
                          <>
                            {drawnPoints.length >= 2 && (
                                <Polyline
                                    path={drawnPoints}
                                    options={{
                                      strokeColor: "#1976d2",
                                      strokeOpacity: 0.8,
                                      strokeWeight: 3,
                                    }}
                                />
                            )}

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
                                  <div style={{ transform: "translate(-50%, -50%)", color: "#4caf50" }}>
                                    <RoomIcon fontSize="large" />
                                  </div>
                                </OverlayView>
                            )}
                          </>
                        }
                    />
                  </Box>
                  <Typography variant="body2" sx={{ color: "text.secondary" }}>
                    Map shows real-time drone position for situational awareness while flying manually.
                  </Typography>
                </Stack>

                {/* Right column: controls */}
                <Box
                    sx={{
                      width: { xs: "100%", md: controlFrameExpanded ? 500 : 360 },
                      transition: "width 180ms ease",
                    }}
                >
                  <Stack spacing={0.5}>
                    {/* Drone command box */}
                    <Paper variant="outlined" sx={{ p: 1, borderRadius: 2 }}>
                      <Stack spacing={0.5}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                          Drone control
                        </Typography>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          <Button
                              variant="contained"
                              color={droneManualConnected ? "success" : "primary"}
                              disabled={connecting || droneManualConnected}
                              onClick={connectDrone}
                          >
                            {connecting ? <><CircularProgress size={16} sx={{ mr: 1 }} /> Connecting…</> : droneManualConnected ? "Drone connected" : "Connect drone"}
                          </Button>
                          <Button
                              variant="contained"
                              color="success"
                              disabled={!droneManualConnected}
                              onClick={runControlledPreflightCheck}
                          >
                            Run preflight check
                          </Button>
                          <Button
                              variant={manualControlEnabled ? "outlined" : "contained"}
                              color={manualControlEnabled ? "warning" : "primary"}
                              disabled={!manualControlReady && !manualControlEnabled}
                              onClick={() => {
                                if (manualControlEnabled) {
                                  setManualControlEnabled(false);
                                  stopAllManualCommands();
                                  return;
                                }
                                setManualControlEnabled(true);
                                setManualControlError(null);
                              }}
                          >
                            {manualControlEnabled ? "Disable keyboard" : "Enable keyboard"}
                          </Button>
                          <Button
                              variant="outlined"
                              color="error"
                              disabled={activeManualCommands.length === 0}
                              onClick={() => stopAllManualCommands("button")}
                          >
                            Stop movement
                          </Button>
                        </Stack>
                        <Chip
                            size="small"
                            color={
                              controlledPreflight == null
                                  ? "default"
                                  : controlledPreflight.passed
                                      ? "success"
                                      : "error"
                            }
                            label={
                              controlledPreflight == null
                                  ? "Not checked"
                                  : controlledPreflight.passed
                                      ? "GREEN — Ready"
                                      : "BLOCKED"
                            }
                        />
                      </Stack>
                    </Paper>

                    <TaskControlFrame
                        expanded={controlFrameExpanded}
                        onExpandedChange={setControlFrameExpanded}
                    >
                        <MissionPreflightPanel
                            apiBase={API_BASE_CLEAN}
                            missionType="controlled"
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
                    </TaskControlFrame>

                    {/* Controlled preflight detail panel */}
                    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
                      <Stack spacing={1.5}>
                        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                          Preflight checks
                        </Typography>

                        {controlledPreflight?.checks?.length ? (
                            <Stack spacing={1}>
                              {controlledPreflight.checks.map((check) => (
                                  <Paper
                                      key={check.id}
                                      variant="outlined"
                                      sx={{
                                        px: 1.25,
                                        py: 1,
                                        borderRadius: 1.5,
                                        borderColor: check.ok ? "success.light" : "error.light",
                                      }}
                                  >
                                    <Stack
                                        direction={{ xs: "column", sm: "row" }}
                                        spacing={1}
                                        justifyContent="space-between"
                                        alignItems={{ xs: "flex-start", sm: "center" }}
                                    >
                                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                        {check.label}
                                      </Typography>
                                      <Chip
                                          size="small"
                                          color={check.ok ? "success" : "error"}
                                          label={check.ok ? "Green" : "Blocked"}
                                      />
                                    </Stack>
                                    <Typography variant="caption" sx={{ color: "text.secondary" }}>
                                      {check.detail}
                                    </Typography>
                                  </Paper>
                              ))}
                            </Stack>
                        ) : (
                            <Alert severity="info">
                              No preflight check has been run yet. Connect the drone and click "Run
                              preflight check".
                            </Alert>
                        )}

                        {manualControlEnabled ? (
                            <Alert severity="success">
                              Keyboard active — W/A/S/D or arrows to move, Q/E yaw, R/F altitude, Space hold, T takeoff, L land.
                            </Alert>
                        ) : (
                            <Alert severity={manualControlReady ? "warning" : "info"}>
                              {manualControlReady
                                  ? "Preflight is green. Enable keyboard control to start flying."
                                  : "Keyboard control stays locked until all preflight checks pass."}
                            </Alert>
                        )}

                        {manualControlError && <Alert severity="error">{manualControlError}</Alert>}

                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                          <Chip size="small" label="W / ↑ Forward" variant="outlined" />
                          <Chip size="small" label="S / ↓ Backward" variant="outlined" />
                          <Chip size="small" label="A / ← Left" variant="outlined" />
                          <Chip size="small" label="D / → Right" variant="outlined" />
                          <Chip size="small" label="Q / E Yaw" variant="outlined" />
                          <Chip size="small" label="R / F Altitude" variant="outlined" />
                          <Chip size="small" label="Space Hold" variant="outlined" />
                          <Chip size="small" label="T Takeoff" variant="outlined" />
                          <Chip size="small" label="L Land" variant="outlined" />
                        </Stack>

                        <Box
                            sx={{
                              display: "grid",
                              gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
                              gap: 1,
                            }}
                        >
                          {MANUAL_CONTROL_BUTTONS.map((button) => {
                            const isActive = activeManualCommands.includes(button.command);
                            return (
                                <Button
                                    key={button.id}
                                    variant={isActive ? "contained" : "outlined"}
                                    color={button.command === "hold" ? "warning" : "primary"}
                                    disabled={!manualControlReady}
                                    onMouseDown={() => beginManualControl(button.id, button.command, "button")}
                                    onMouseUp={() => endManualControl(button.id, "button")}
                                    onMouseLeave={() => endManualControl(button.id, "button")}
                                    onTouchStart={() => beginManualControl(button.id, button.command, "button")}
                                    onTouchEnd={() => endManualControl(button.id, "button")}
                                    sx={{ minHeight: 56 }}
                                >
                                  <Stack spacing={0.25}>
                                    <Typography variant="button">{button.label}</Typography>
                                    <Typography variant="caption">{button.hint}</Typography>
                                  </Stack>
                                </Button>
                            );
                          })}
                        </Box>

                        {lastManualCommand && (
                            <Typography variant="caption" sx={{ color: "text.secondary" }}>
                              Last: {lastManualCommand.command} ({lastManualCommand.phase})
                              via {lastManualCommand.source} at{" "}
                              {new Date(lastManualCommand.sentAt).toLocaleTimeString()}.
                            </Typography>
                        )}
                      </Stack>
                    </Paper>

                    {/* Mission session form */}
                    <TextField
                        variant="filled"
                        label="Session name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        size="small"
                        fullWidth
                        required
                        error={!name.trim()}
                        helperText={!name.trim() ? "Session name is required" : " "}
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
                              : " "
                        }
                    />

                    <Button
                        variant="contained"
                        onClick={sendMission}
                        disabled={
                            sending ||
                            !name.trim() ||
                            altInput === "" ||
                            Number(altInput) < 1 ||
                            Number(altInput) > 500
                        }
                        fullWidth
                        sx={{ mt: 1 }}
                        color="success"
                    >
                      {sending ? (
                          <>
                            <CircularProgress size={20} sx={{ mr: 1 }} />
                            Starting session...
                          </>
                      ) : (
                          "Start Controlled Flight Session"
                      )}
                    </Button>

                    {activeFlightId && (
                        <Alert severity="info" sx={{ mt: 1 }}>
                          Active flight: {missionStatus?.mission_name || activeFlightId}
                        </Alert>
                    )}

                    {/* Flight status */}
                    {missionStatus && activeFlightId && (
                        <Box sx={{ p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: "bold", mb: 1 }}>
                            Flight Status
                          </Typography>
                          <Stack spacing={0.5}>
                            {missionStatus.flight_id && (
                                <Typography variant="caption" component="div">
                                  Flight ID: {missionStatus.flight_id}
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
                            {batteryPercent != null && (
                                <Typography variant="caption" component="div">
                                  Battery: {batteryPercent.toFixed(0)}%
                                </Typography>
                            )}
                            {gpsFixType != null && (
                                <Typography variant="caption" component="div">
                                  GPS Fix: {gpsFixType}
                                </Typography>
                            )}
                          </Stack>
                        </Box>
                    )}
                  </Stack>
                </Box>
              </Stack>
          )}
        </Paper>
      </>
  );
}
