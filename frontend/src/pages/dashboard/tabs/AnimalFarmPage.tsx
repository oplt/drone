import { useEffect, useRef, useState, useCallback, useMemo, useContext } from "react";
import { Box, Button, Paper, Stack, Typography, Divider, TextField, Alert, CircularProgress, MenuItem,  Select,
  FormControl, InputLabel} from "@mui/material";
import Header from "../../../components/dashboard/Header";
import { Polyline, OverlayView } from "@react-google-maps/api";
import { getToken } from "../../../auth";
import DroneSvg from "../../../assets/Drone.svg?react";
import SvgIcon from "@mui/material/SvgIcon";
import RoomIcon from "@mui/icons-material/Room";
import { GoogleMapsContext } from "../../../utils/googleMaps";
import { CesiumViewControls } from "../../../components/dashboard/tasks/CesiumViewControls";
import { ErrorAlerts } from "../../../components/dashboard/tasks/ErrorAlerts";
import { MissionCommandPanel } from "../../../components/dashboard/tasks/MissionCommandPanel";
import { MissionMapViewport } from "../../../components/dashboard/tasks/MissionMapViewport";
import { MissionVideoPanel } from "../../../components/dashboard/tasks/MissionVideoPanel";
import { MissionStatusChips } from "../../../components/dashboard/tasks/MissionStatusChips";
import { useDroneCenter } from "../../../hooks/useDroneCenter";
import { useDroneMapFollow } from "../../../hooks/useDroneMapFollow";
import { useErrors } from "../../../hooks/useErrors";
import { useAutoStartVideo } from "../../../hooks/useAutoStartVideo";
import { useMissionCommandMetrics } from "../../../hooks/useMissionCommandMetrics";
import { useMissionWebsocketRuntime } from "../../../hooks/useMissionWebsocketRuntime";
import { type LatLng } from "../../../lib/extractLatLng";


type Waypoint = { lat: number; lon: number; alt: number };
type CesiumViewMode = "top" | "tilted" | "follow" | "fpv" | "orbit";

type Herd = {
  id: number;
  name: string;
  pasture_geofence_id?: number | null;
};

type HerdLatestPos = {
  animal_id: number;
  collar_id: string;
  animal_name?: string | null;
  species: string;
  lat: number;
  lon: number;
  alt?: number | null;
  created_at: string;
};

type HerdAlert = {
  type: string; // "boundary_exit" | "isolation" | ...
  severity: "low" | "medium" | "high";
  animal_id: number;
  collar_id: string;
  lat: number;
  lon: number;
  message: string;
  distance_to_nearest_m?: number;
};




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
  const mapRef = useRef<google.maps.Map | null>(null);

  const [userCenter, setUserCenter] = useState<LatLng | null>(null);
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);

  // altitude: keep input string to avoid error spam while typing
  const [alt, setAlt] = useState<number>(30);
  const [altInput, setAltInput] = useState<string>("30");

  const [name, setName] = useState<string>("field-plan-1");
  const [sending, setSending] = useState(false);
  const [center, setCenter] = useState<LatLng>(defaultCenter);
  const [loadingLocation, setLoadingLocation] = useState(true);

  const { errors, addError, clearErrors, dismissError } = useErrors();

  const [mapZoom, setMapZoom] = useState<number>(12);

  const [streamKey, setStreamKey] = useState<number>(Date.now());
  const [mapReady, setMapReady] = useState(false);
  const videoToken = getToken();
  const waypointMarkersRef = useRef<any[]>([]);
  const [useCesium, setUseCesium] = useState(false);
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
    disconnect,
    droneConnected,
  } = useMissionWebsocketRuntime<MissionStatus>({
    apiBase: API_BASE_CLEAN,
    getTokenFn: getToken,
    onError: addError,
  });
  const droneCenter = useDroneCenter(telemetry);
  const { heading, armed } = useMissionCommandMetrics(telemetry);

    const handleCesiumPick = useCallback((p: { lat: number; lng: number }) => {
      setWaypoints((prev) => [...prev, { lat: p.lat, lon: p.lng, alt }]);
    }, [alt]);
  const droneReady = Boolean(wsConnected && droneCenter);
  const { startingVideo, streamKey: autoStreamKey } = useAutoStartVideo({
    apiBase: API_BASE_CLEAN,
    getToken,
    enabled: droneReady,
    onError: addError,
    resetKey: activeFlightId ?? "none",
  });
  const { isLoaded, loadError } = useContext(GoogleMapsContext);

const [herds, setHerds] = useState<Herd[]>([]);
const [selectedHerdId, setSelectedHerdId] = useState<number | null>(null);

const [latestPositions, setLatestPositions] = useState<HerdLatestPos[]>([]);
const [herdAlerts, setHerdAlerts] = useState<HerdAlert[]>([]);

const [loadingHerdOps, setLoadingHerdOps] = useState(false);
const [collarIdForSearch, setCollarIdForSearch] = useState<string>("");

  useEffect(() => {
    if (autoStreamKey) setStreamKey(autoStreamKey);
  }, [autoStreamKey]);

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


  // Get user location on mount
  useEffect(() => {
    if (!navigator.geolocation) {
      console.warn("Geolocation is not supported by this browser.");
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
        console.error("Error getting location:", error);
        addError(`Failed to get location: ${error.message}`);
        setLoadingLocation(false);
      },
      {
        enableHighAccuracy: true,
        timeout: 5000,
        maximumAge: 0,
      },
    );
  }, [addError]);


    const handleVideoError = useCallback(() => {
      setVideoError("Failed to load video stream");
      setVideoRetryCount(prev => prev + 1);

      // Auto-retry after 5 seconds
      setTimeout(() => {
        setStreamKey(Date.now()); // Force reload with new key
        setVideoError(null);
      }, 5000);
    }, []);

    // Add video load success handler
    const handleVideoLoad = useCallback(() => {
      setVideoError(null);
      setVideoRetryCount(0);
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

  const r = await fetch(`${API_BASE_CLEAN}/livestock/herds`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(await r.text().catch(() => "") || `HTTP ${r.status}`);
  const data = (await r.json()) as Herd[];
  setHerds(data);

  // Auto-select first herd if none selected
  if (!selectedHerdId && data.length > 0) setSelectedHerdId(data[0].id);
}, [API_BASE_CLEAN, selectedHerdId]);

const fetchLatestPositions = useCallback(async (herdId: number) => {
  const token = getToken();
  if (!token) return;

  const r = await fetch(`${API_BASE_CLEAN}/livestock/herds/${herdId}/latest_positions`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(await r.text().catch(() => "") || `HTTP ${r.status}`);
  const data = await r.json();
  setLatestPositions((data?.positions ?? []) as HerdLatestPos[]);
}, [API_BASE_CLEAN]);

const fetchRisk = useCallback(async (herdId: number) => {
  const token = getToken();
  if (!token) return;

  const r = await fetch(`${API_BASE_CLEAN}/livestock/herds/${herdId}/risk`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(await r.text().catch(() => "") || `HTTP ${r.status}`);
  const data = await r.json();
  setHerdAlerts((data?.alerts ?? []) as HerdAlert[]);
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

  const onMapClick = useCallback(
    (e: google.maps.MapMouseEvent) => {
      if (!e.latLng) return;
      const lat = e.latLng.lat();
      const lng = e.latLng.lng();
      setWaypoints((prev) => [...prev, { lat, lon: lng, alt }]);
    },
    [alt],
  );

  const undo = () => setWaypoints((prev) => prev.slice(0, -1));
  const clear = () => setWaypoints([]);

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
        // Create and start mission - orchestrator handles telemetry internally
        const missionRes = await fetch(`${API_BASE_CLEAN}/tasks/missions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            name: name.trim(),
            cruise_alt: altToUse,
            waypoints: waypoints.map(wp => ({
              lat: wp.lat,
              lon: wp.lon,
              alt: wp.alt
            })),
          }),
        });

        if (!missionRes.ok) {
          const error = await missionRes.text();
          throw new Error(error || "Failed to create flight plan");
        }

        const data = await missionRes.json();
        alert(`Flight plan "${data.mission_name}" started! Tracking flight...`);

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
    const taskRes = await fetch(`${API_BASE_CLEAN}/livestock/tasks`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ herd_id: selectedHerdId, type, params }),
    });
    if (!taskRes.ok) throw new Error(await taskRes.text().catch(() => "") || "Failed to create task");
    const task = await taskRes.json();

    // 2) Plan mission
    const planRes = await fetch(`${API_BASE_CLEAN}/livestock/tasks/${task.id}/plan`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!planRes.ok) throw new Error(await planRes.text().catch(() => "") || "Failed to plan mission");
    const plan = await planRes.json();

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
    if (waypoints.length > 0) {
      return { lat: waypoints[0].lat, lng: waypoints[0].lon };
    }
    return userCenter || center;
  }, [waypoints, userCenter, center]);

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

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              variant="contained"
              onClick={() => createTaskAndPlan("census")}
              disabled={!selectedHerdId || loadingHerdOps}
            >
              Plan Census
            </Button>
            <Button
              variant="contained"
              onClick={() => createTaskAndPlan("herd_sweep")}
              disabled={!selectedHerdId || loadingHerdOps}
            >
              Plan Herd Sweep
            </Button>
          </Stack>

          <Stack direction="row" spacing={1}>
            <TextField variant="filled"
              size="small"
              label="Collar ID (optional)"
              value={collarIdForSearch}
              onChange={(e) => setCollarIdForSearch(e.target.value)}
              fullWidth
            />
            <Button
              variant="outlined"
              onClick={() => createTaskAndPlan("search_locate")}
              disabled={!selectedHerdId || loadingHerdOps}
            >
              Search
            </Button>
          </Stack>

          <Divider />

          <Stack direction="row" spacing={1} alignItems="center">
            <Button
              size="small"
              variant="text"
              onClick={() => selectedHerdId && fetchLatestPositions(selectedHerdId)}
              disabled={!selectedHerdId}
            >
              Refresh positions
            </Button>
            <Button
              size="small"
              variant="text"
              onClick={() => selectedHerdId && fetchRisk(selectedHerdId)}
              disabled={!selectedHerdId}
            >
              Refresh risk
            </Button>
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
          background:
            "linear-gradient(135deg, hsla(174, 50%, 95%, 0.8), hsla(36, 40%, 96%, 0.9))",
          border: "1px solid hsla(174, 30%, 40%, 0.2)",
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
            <Stack direction={{ xs: "column", md: "row" }} spacing={3} sx={{ mb: 3 }}>
              {/* Left side: Map & Camera */}
              <Stack sx={{ flex: 1, minHeight: 200 }} spacing={2}>


                <Box
                  sx={{
                    borderRadius: 2,
                    overflow: "hidden",
                    border: "1px solid hsla(174, 30%, 40%, 0.2)",
                    backgroundColor: "background.paper",
                  }}
                >
                  <MissionMapViewport
                    loadingLocation={loadingLocation}
                    isLoaded={isLoaded}
                    useCesium={useCesium}
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
                      droneCenter,
                      headingDeg: typeof heading === "number" ? heading : null,
                      onPickLatLng: handleCesiumPick,
                    }}
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
                                fontSize: 12
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

                <Box
                  sx={{
                    mt: 2,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: 2,
                  }}
                >
                  <CesiumViewControls
                    useCesium={useCesium}
                    onUseCesiumChange={setUseCesium}
                    viewMode={cesiumViewMode}
                    onViewModeChange={setCesiumViewMode}
                  />
                </Box>


                <Typography variant="body2" sx={{ mt: 1 }}>
                  Click on the map to add waypoints. Markers are ordered (1..N).
                </Typography>

                <MissionVideoPanel
                  title="Survey Camera"
                  imgAlt="Survey camera stream"
                  disconnectedMessage="Connect the drone to view the survey stream."
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
              </Stack>

              {/* Right side: Controls */}
              <Box sx={{ width: { xs: "100%", md: 300 } }}>
                <Stack spacing={2}>
                  <MissionCommandPanel telemetry={telemetry} droneConnected={droneConnected} />
                  <TextField variant="filled"
                    label="Field plan name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    size="small"
                    fullWidth
                    required
                    error={!name.trim()}
                    helperText={!name.trim() ? "Field plan name is required" : ""}
                  />

                  <TextField variant="filled"
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

                  <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                    <Button
                      variant="outlined"
                      onClick={undo}
                      disabled={waypoints.length === 0 || sending}
                      fullWidth
                    >
                      Undo Last
                    </Button>
                    <Button
                      variant="outlined"
                      onClick={clear}
                      disabled={waypoints.length === 0 || sending}
                      fullWidth
                      color="error"
                    >
                      Clear All
                    </Button>
                  </Stack>

                  <Button
                    variant="contained"
                    onClick={sendMission}
                    disabled={
                      sending ||
                      waypoints.length < 2 ||
                      !name.trim() ||
                      altInput === "" ||
                      Number(altInput) < 1 ||
                      Number(altInput) > 500
                    }
                    fullWidth
                    sx={{ mt: 2 }}
                  >
                    {sending ? (
                      <>
                        <CircularProgress size={20} sx={{ mr: 1 }} />
                        Sending...
                      </>
                    ) : (
                      "Start Flight Plan"
                    )}
                  </Button>

                  {activeFlightId && (
                    <Alert severity="info" sx={{ mt: 2 }}>
                      Active flight: {missionStatus?.mission_name || "Loading..."}
                    </Alert>
                  )}
                </Stack>
              </Box>
            </Stack>

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
              <Box sx={{ mt: 2, p: 2, bgcolor: "#e8f5e8", borderRadius: 1 }}>
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
    </>
  );
}
