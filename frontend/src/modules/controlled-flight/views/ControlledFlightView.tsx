import { useEffect, useRef, useState, useCallback, useMemo, useContext } from "react";
import {
  Box,
  Chip,
  Paper,
  Stack,
  TextField,
  Alert,
  Typography,
} from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
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
import {
  TaskPreflightCommandsDrawer,
  useTaskPreflightCommandsDrawer,
} from "../../../modules/mission-workflow";
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
import { fetchFlightStatus } from "../../mission-runtime/api/missionsApi";
import type { TerraDraw } from "terra-draw";
import { connectDroneTelemetry } from "../../mission-runtime/api/telemetryConnectApi";
import { useControlledPreflight } from "../hooks/useControlledPreflight";
import { useManualFlightControls } from "../hooks/useManualFlightControls";
import { ManualFlightControlPanel } from "../components/ManualFlightControlPanel";
import {
  readNestedValue,
  firstFiniteNumber,
} from "../utils/telemetryHealth";

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

export function ControlledFlightView() {
  const preflightCommandsDrawer = useTaskPreflightCommandsDrawer();
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
  const [streamKey, setStreamKey] = useState(() => Date.now());
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
  }, [addError]);

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

  const runManualPreflightCheck = useCallback(async () => {
    const token = getToken();
    if (!token) {
      addError("Not authenticated");
      return;
    }
    setConnecting(true);
    try {
      if (!missionStatus?.telemetry?.running || !droneConnected) {
        await connectDroneTelemetry(token);
      }
      setDroneManualConnected(true);
      await new Promise((resolve) => window.setTimeout(resolve, 600));
      const refreshedStatus = await fetchFlightStatus<MissionStatus>(token);
      runControlledPreflightCheck({
        droneConnected:
          droneConnected || Boolean(refreshedStatus?.orchestrator?.drone_connected),
        wsConnected: wsConnected || Boolean(refreshedStatus?.telemetry?.running),
        missionStatus: refreshedStatus,
      });
    } catch (error) {
      addError(error instanceof Error ? error.message : "Preflight check failed");
    } finally {
      setConnecting(false);
    }
  }, [
    addError,
    droneConnected,
    missionStatus?.telemetry?.running,
    runControlledPreflightCheck,
    wsConnected,
  ]);

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

  const mapCenter = useMemo(
    () => droneCenter || userCenter || center,
    [droneCenter, userCenter, center]
  );
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
                      width: { xs: "100%", md: 360 },
                    }}
                >
                  <Stack spacing={0.5}>
                    {/* Drone command box */}
                    <Paper variant="outlined" sx={{ p: 1, borderRadius: 2 }}>
                      <Stack spacing={0.5}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                          Drone control
                        </Typography>
                        <Stack direction="row" spacing={0.25} flexWrap="wrap" useFlexGap>
                          <ActionIconButton
                            variant="connect"
                            title={connecting ? "Connecting…" : droneManualConnected ? "Drone connected" : "Connect drone"}
                            color={droneManualConnected ? "success" : "primary"}
                            loading={connecting}
                            disabled={connecting || droneManualConnected}
                            onClick={connectDrone}
                          />
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

                    <ManualFlightControlPanel
                        controlledPreflight={controlledPreflight}
                        manualControlEnabled={manualControlEnabled}
                        manualControlReady={manualControlReady}
                        manualControlError={manualControlError}
                        activeManualCommands={activeManualCommands}
                        lastManualCommand={lastManualCommand}
                        preflightBusy={connecting}
                        onRunPreflight={() => {
                          void runManualPreflightCheck();
                        }}
                        onToggleKeyboard={() => {
                          if (manualControlEnabled) {
                            setManualControlEnabled(false);
                            stopAllManualCommands();
                            return;
                          }
                          setManualControlEnabled(true);
                          setManualControlError(null);
                        }}
                        onStopMovement={() => stopAllManualCommands("button")}
                        beginManualControl={beginManualControl}
                        endManualControl={endManualControl}
                    />

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

                    <Stack direction="row" justifyContent="flex-end" sx={{ mt: 1 }}>
                      <ActionIconButton
                        variant="play"
                        title={sending ? "Starting session…" : "Start Controlled Flight Session"}
                        color="success"
                        size="medium"
                        loading={sending}
                        disabled={
                          sending ||
                          !name.trim() ||
                          altInput === "" ||
                          Number(altInput) < 1 ||
                          Number(altInput) > 500
                        }
                        onClick={sendMission}
                      />
                    </Stack>

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

        <TaskPreflightCommandsDrawer
          open={preflightCommandsDrawer.open}
          onOpenChange={preflightCommandsDrawer.onOpenChange}
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
        </TaskPreflightCommandsDrawer>
      </>
  );
}
