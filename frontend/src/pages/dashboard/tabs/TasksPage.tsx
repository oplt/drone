import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
  Box,
  Button,
  Paper,
  Stack,
  Typography,
  Divider,
  TextField,
  Alert,
  CircularProgress,
  Chip,
} from "@mui/material";
import Header from "../components/Header";
import {
  GoogleMap,
  Polyline,
  OverlayView,
  useJsApiLoader,
} from "@react-google-maps/api";
import { getToken } from "../../../auth"; // adjust path if needed
import DroneSvg from "../../../assets/Drone.svg?react";
import SvgIcon from "@mui/material/SvgIcon";
import RoomIcon from "@mui/icons-material/Room";
import useTelemetryWebSocket from "../../../hooks/useTelemetryWebsocket";

type LatLng = { lat: number; lng: number };
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

// Try to safely extract lat/lon from whatever the backend publishes
function extractLatLng(value: any): LatLng | null {
  if (!value) return null;

  const lat =
    value.lat ??
    value.latitude ??
    value.Lat ??
    value.Latitude ??
    (value.position ? value.position.lat ?? value.position.latitude : undefined);

  const lon =
    value.lon ??
    value.lng ??
    value.longitude ??
    value.Lon ??
    value.Lng ??
    value.Longitude ??
    (value.position
      ? value.position.lon ?? value.position.lng ?? value.position.longitude
      : undefined);

  if (typeof lat !== "number" || typeof lon !== "number") return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (lat < -90 || lat > 90) return null;
  if (lon < -180 || lon > 180) return null;

  return { lat, lng: lon };
}

const containerStyle = { width: "100%", height: "400px" };
const defaultCenter = { lat: 50.8503, lng: 4.3517 };

export default function TasksPage() {
  const mapRef = useRef<google.maps.Map | null>(null);

  // IMPORTANT: refs for cleanup to avoid “cleanup runs on dependency change” bug
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeFlightIdRef = useRef<string | null>(null);
  const missionStartAtRef = useRef<number | null>(null);

  // animation + panning control
  const rafRef = useRef<number | null>(null);
  const lastPanRef = useRef<number>(0);
  const snappedToDroneRef = useRef(false);

  const [userCenter, setUserCenter] = useState<LatLng | null>(null);
  const [droneCenter, setDroneCenter] = useState<LatLng | null>(null);
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);

  // altitude: keep input string to avoid error spam while typing
  const [alt, setAlt] = useState<number>(30);
  const [altInput, setAltInput] = useState<string>("30");

  const [name, setName] = useState<string>("field-plan-1");
  const [sending, setSending] = useState(false);
  const [center, setCenter] = useState<LatLng>(defaultCenter);
  const [loadingLocation, setLoadingLocation] = useState(true);

  const videoStartedRef = useRef(false);
  const [activeFlightId, setActiveFlightId] = useState<string | null>(null);
  const [missionStatus, setMissionStatus] = useState<MissionStatus | null>(null);

  const [mapZoom, setMapZoom] = useState<number>(12);

  const [streamKey, setStreamKey] = useState<number>(Date.now());
  const [startingVideo, setStartingVideo] = useState<boolean>(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [mapReady, setMapReady] = useState(false);
  const videoToken = getToken();
  const waypointMarkersRef = useRef<any[]>([]);

  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY as string;
  const mapId = (import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string) || "";
  const API_BASE_RAW = import.meta.env.VITE_API_BASE_URL ?? "";
  const API_BASE_CLEAN = (API_BASE_RAW || "http://localhost:8000").replace(/\/$/, "");
  const libraries = useMemo(() => ["marker"] as any, []);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoRetryCount, setVideoRetryCount] = useState(0);
  const wsEnabled = Boolean(
    missionStatus?.orchestrator?.drone_connected &&
      missionStatus?.telemetry?.running &&
      activeFlightId,
  );
  const { telemetry, isConnected: wsConnected, disconnect } = useTelemetryWebSocket(
    {
      enabled: wsEnabled,
    },
  );
  const droneConnected = Boolean(
    missionStatus?.orchestrator?.drone_connected || wsConnected,
  );
  const droneReady = Boolean(wsConnected && droneCenter);
  // Removes LoadScript + prevents repeated script injection
  const { isLoaded, loadError } = useJsApiLoader({
    id: "google-maps-script",
    googleMapsApiKey: apiKey || "MISSING_KEY",
    libraries,
  });

  // Keep latest activeFlightId in a ref for unmount cleanup
  useEffect(() => {
    activeFlightIdRef.current = activeFlightId;
  }, [activeFlightId]);

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

  const addError = useCallback((error: string) => {
    setErrors((prev) => [...prev.slice(-4), error]); // keep last 5
  }, []);

  const clearErrors = useCallback(() => {
    setErrors([]);
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


  // Extract drone position from telemetry (handles multiple possible shapes)
  useEffect(() => {
    const next =
      extractLatLng(telemetry?.position) ||
      extractLatLng(telemetry?.gps) ||
      extractLatLng(telemetry?.home) ||
      extractLatLng(telemetry);

    if (!next) return;

    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => setDroneCenter(next));

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [telemetry]);


/*
  // Fallback: use last known position from flight status when WS is not yet streaming
  useEffect(() => {
    const statusPosition = missionStatus?.telemetry?.position;
    const hasPosition = Boolean(missionStatus?.telemetry?.has_position_data);
    if (!statusPosition || !hasPosition) return;
    if (wsConnected && droneCenter) return;

    const next = extractLatLng(statusPosition);
    if (!next) return;

    if (
      droneCenter &&
      Math.abs(droneCenter.lat - next.lat) < 1e-7 &&
      Math.abs(droneCenter.lng - next.lng) < 1e-7
    ) {
      return;
    }

    setDroneCenter(next);
  }, [missionStatus, wsConnected, droneCenter]);

*/

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

  useEffect(() => {
    if (!activeFlightId) {
      videoStartedRef.current = false;
    }
  }, [activeFlightId]);

  // Start Pi camera streaming when drone becomes ready (best effort)
  useEffect(() => {
    const token = getToken();
    if (!droneReady || !token || videoStartedRef.current) return;

    const timer = setTimeout(() => {
      setStartingVideo(true);
      fetch(`${API_BASE_CLEAN}/video/start`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(async (res) => {
          if (!res.ok) {
            let detail = `HTTP ${res.status}`;
            try {
              const data = (await res.json()) as { detail?: string };
              if (data?.detail) detail = data.detail;
            } catch {
              // ignore
            }
            throw new Error(detail);
          }
          setStreamKey(Date.now());
          videoStartedRef.current = true;
        })
        .catch((error) => {
          addError(`Failed to start video: ${error.message}`);
        })
        .finally(() => {
          setStartingVideo(false);
        });
    }, 1000);

    return () => clearTimeout(timer);
  }, [droneReady, API_BASE_CLEAN, addError]);

  const pollFlightStatus = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    try {
      const res = await fetch(`${API_BASE_CLEAN}/tasks/flight/status`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const status = (await res.json()) as MissionStatus;
      setMissionStatus(status);

      if (!status.flight_id) {
        // backend may lag before reporting a flight_id; keep local ID briefly
        const graceMs = 30000;
        const startedAt = missionStartAtRef.current ?? 0;
        const withinGrace = startedAt > 0 && Date.now() - startedAt < graceMs;
        if (!withinGrace) {
          setActiveFlightId(null);
        }
        return;
      }

      if (status.flight_id !== activeFlightIdRef.current) {
        setActiveFlightId(status.flight_id);
        missionStartAtRef.current = Date.now();
      }
    } catch (error) {
      console.error("Failed to poll flight status:", error);
      addError(
        `Flight status polling failed: ${
          error instanceof Error ? error.message : "Unknown error"
        }`,
      );
    }
  }, [API_BASE_CLEAN, addError]);

  // Poll flight status continuously so telemetry/drone readiness is known even before a mission
  useEffect(() => {
    pollFlightStatus();

    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    pollIntervalRef.current = setInterval(pollFlightStatus, 5000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [pollFlightStatus]);

  // Cleanup on unmount ONLY (stop telemetry, clear polling, disconnect WS)
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }

      disconnect();
    };
  }, [disconnect]);

  // Focus map on drone once (as soon as we get a valid position)
  useEffect(() => {
    if (!mapRef.current || !droneCenter) return;

    if (!snappedToDroneRef.current) {
      snappedToDroneRef.current = true;
      mapRef.current.panTo(droneCenter);
      mapRef.current.setZoom(18);
      setMapZoom(18);
    }
  }, [droneCenter]);

  useEffect(() => {
    if (!wsConnected) snappedToDroneRef.current = false;
  }, [wsConnected]);

  // During flight, keep following in a non-invasive way (only when zoomed-in already)
  useEffect(() => {
    if (!mapRef.current || !droneCenter || !wsConnected) return;

    const now = Date.now();
    if (now - lastPanRef.current < 500) return; // max 2x/sec
    lastPanRef.current = now;

    const currentZoom = mapRef.current.getZoom() ?? 0;
    if (currentZoom < 16) return;

    mapRef.current.panTo(droneCenter);
  }, [droneCenter, wsConnected]);

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

        setActiveFlightId(data.flight_id);
        missionStartAtRef.current = Date.now();

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

  // --- Telemetry overlay values (best-effort extraction) ---
  const batteryPctRaw =
    telemetry?.battery?.percent ??
    telemetry?.battery?.percentage ??
    telemetry?.battery?.remaining ??
    telemetry?.battery_remaining ??
    telemetry?.batteryPercent ??
    null;
  const batteryPct =
    typeof batteryPctRaw === "number" && batteryPctRaw >= 0
      ? batteryPctRaw
      : null;

  const groundSpeed =
    telemetry?.velocity?.ground ??
    telemetry?.status?.groundspeed ??
    telemetry?.ground_speed ??
    telemetry?.groundSpeed ??
    telemetry?.speed ??
    null;

  const relAlt =
    telemetry?.position?.rel_alt_m ??
    telemetry?.position?.relative_altitude ??
    telemetry?.position?.relative_alt ??
    telemetry?.altitude ??
    telemetry?.relativeAltitude ??
    null;

  const heading =
    telemetry?.status?.heading ?? telemetry?.heading ?? telemetry?.yaw ?? null;

  const mode =
    telemetry?.status?.mode ?? telemetry?.mode ?? telemetry?.flight_mode ?? null;

  const sats = telemetry?.gps?.satellites ?? telemetry?.satellites ?? null;
  const hdop =
    telemetry?.gps?.hdop ?? telemetry?.hdop ?? telemetry?.gps_hdop ?? null;

  const armed = Boolean(telemetry?.armed ?? telemetry?.status?.armed);

  const batteryCellsRaw =
    telemetry?.battery?.cells ??
    telemetry?.battery?.cell_voltages ??
    telemetry?.battery_cells ??
    telemetry?.cell_voltages ??
    null;

  const batteryCells = Array.isArray(batteryCellsRaw) ? batteryCellsRaw : null;

  const linkRc =
    telemetry?.link?.rc ??
    telemetry?.rc?.quality ??
    telemetry?.rc_quality ??
    telemetry?.rssi ??
    null;

  const linkLte =
    telemetry?.link?.lte ??
    telemetry?.lte?.quality ??
    telemetry?.lte_quality ??
    null;

  const linkTelemetry =
    telemetry?.link?.telemetry ??
    telemetry?.telemetry?.quality ??
    telemetry?.telemetry_quality ??
    null;

  const windSpeed =
    telemetry?.wind?.speed ??
    telemetry?.wind_speed ??
    telemetry?.windSpeed ??
    null;

  const failsafeRaw =
    telemetry?.failsafe?.state ??
    telemetry?.failsafe_state ??
    telemetry?.status?.failsafe ??
    null;

  const formatMaybeNumber = (v: any, digits = 1) =>
    typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "--";

  const formatMaybePercent = (v: any) =>
    typeof v === "number" && Number.isFinite(v) ? `${Math.round(v)}%` : "--";

  const batteryHealth =
    typeof batteryPct === "number" && Number.isFinite(batteryPct)
      ? batteryPct >= 60
        ? `Good (${Math.round(batteryPct)}%)`
        : batteryPct >= 30
          ? `Fair (${Math.round(batteryPct)}%)`
          : `Critical (${Math.round(batteryPct)}%)`
      : "--";

  const batteryCellDisplay = batteryCells?.length
    ? batteryCells.map((v) => `${formatMaybeNumber(Number(v), 2)}V`).join(" / ")
    : "--";

  const gpsStrength =
    sats === null && hdop === null
      ? "--"
      : `${sats ?? "--"} sats • HDOP ${formatMaybeNumber(hdop, 1)}`;

  const linkParts: string[] = [];
  if (linkRc !== null && linkRc !== undefined) {
    linkParts.push(`RC ${formatMaybePercent(Number(linkRc))}`);
  }
  if (linkLte !== null && linkLte !== undefined) {
    linkParts.push(`LTE ${formatMaybePercent(Number(linkLte))}`);
  }
  if (linkTelemetry !== null && linkTelemetry !== undefined) {
    linkParts.push(`TEL ${formatMaybePercent(Number(linkTelemetry))}`);
  }
  const linkQuality = linkParts.length > 0 ? linkParts.join(" • ") : "--";

  const failsafeState =
    typeof failsafeRaw === "string" && failsafeRaw.trim() !== ""
      ? failsafeRaw
      : typeof failsafeRaw === "boolean"
        ? failsafeRaw
          ? "Active"
          : "None"
        : "--";

  const failsafeActive =
    typeof failsafeRaw === "boolean"
      ? failsafeRaw
      : typeof failsafeRaw === "string"
        ? !["none", "ok", "inactive"].includes(failsafeRaw.toLowerCase())
        : false;

  const flightStatus = failsafeActive
    ? "Emergency"
    : typeof mode === "string" && mode.toUpperCase().includes("RTL")
      ? "RTL"
      : armed && typeof groundSpeed === "number" && groundSpeed > 1
        ? "In Air"
        : armed
          ? "Armed"
          : "Idle";

  const windDisplay =
    windSpeed === null || windSpeed === undefined
      ? "--"
      : `${formatMaybeNumber(Number(windSpeed), 1)} m/s`;

  const TelemetryBox = ({ label, value }: { label: string; value: string }) => (
    <Box
      sx={{
        px: 1,
        py: 0.5,
        borderRadius: 1,
        bgcolor: "rgba(0,0,0,0.65)",
        color: "white",
        fontSize: 12,
        lineHeight: 1.2,
        minWidth: 88,
      }}
    >
      <div style={{ opacity: 0.85, fontSize: 10 }}>{label}</div>
      <div style={{ fontWeight: 600 }}>{value}</div>
    </Box>
  );

  return (
    <>
      <Header />
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
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              size="small"
              label={droneConnected ? "Drone online" : "Drone offline"}
              color={droneConnected ? "success" : "default"}
              variant={droneConnected ? "filled" : "outlined"}
            />
            <Chip
              size="small"
              label={wsConnected ? "Secure link" : "Link down"}
              color={wsConnected ? "success" : "default"}
              variant={wsConnected ? "filled" : "outlined"}
            />
          </Stack>
        </Stack>

        {/* Error display */}
        {errors.length > 0 && (
          <Box sx={{ mb: 2 }}>
            {errors.map((error, idx) => (
              <Alert
                key={`${idx}-${error}`}
                severity="error"
                sx={{ mb: 1 }}
                onClose={() => setErrors((prev) => prev.filter((_, i) => i !== idx))}
              >
                {error}
              </Alert>
            ))}
            <Button size="small" onClick={clearErrors} sx={{ mt: 1 }}>
              Clear All Errors
            </Button>
          </Box>
        )}

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
                  {loadingLocation ? (
                    <Box
                      sx={{
                        width: "100%",
                        height: 400,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        bgcolor: "hsla(36, 30%, 96%, 0.7)",
                      }}
                    >
                      <CircularProgress />
                      <Typography sx={{ ml: 2 }}>Loading your location...</Typography>
                    </Box>
                  ) : !isLoaded ? (
                    <Box
                      sx={{
                        width: "100%",
                        height: 400,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        bgcolor: "hsla(36, 30%, 96%, 0.7)",
                      }}
                    >
                      <CircularProgress />
                      <Typography sx={{ ml: 2 }}>Loading map...</Typography>
                    </Box>
                  ) : (
                    <GoogleMap
                      mapContainerStyle={containerStyle}
                      center={mapCenter}
                      zoom={mapZoom}
                      onClick={onMapClick}
                      onLoad={onMapLoad}
                      onZoomChanged={onMapZoomChanged}
                      options={mapOptions}
                    >
                    {/* Drone icon (now always visible whenever we have droneCenter) */}
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

                    {/* User location icon */}
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

                    {/* Waypoint markers rendered via AdvancedMarkerElement */}

                    {/* Flight path */}
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
                    </GoogleMap>
                  )}
                </Box>

                <Typography variant="body2" sx={{ mt: 1 }}>
                  Click on the map to add waypoints. Markers are ordered (1..N).
                </Typography>
                <Typography variant="body2" sx={{ mt: 1 }}>
                  Drone Status: {droneConnected ? "Connected" : "Disconnected"}
                  {activeFlightId && ` | Active Flight: ${activeFlightId.substring(0, 8)}...`}
                  {wsConnected && ` | WS: Connected`}
                </Typography>

                {/* Camera stream panel under the map */}
                <Paper
                  variant="outlined"
                  sx={{
                    p: 2,
                    borderRadius: 2,
                    borderColor: "hsla(174, 30%, 40%, 0.25)",
                    background: "hsla(0, 0%, 100%, 0.7)",
                  }}
                >
                  <Stack
                    direction="row"
                    alignItems="center"
                    justifyContent="space-between"
                    sx={{ mb: 1 }}
                  >
                    <Typography variant="subtitle1">Survey Camera</Typography>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      {startingVideo && <CircularProgress size={16} />}
                      <Typography variant="caption" color="text.secondary">
                        {startingVideo
                          ? "Starting video…"
                          : videoError
                            ? "Error"
                            : droneConnected
                              ? "Live"
                              : "Disconnected"}
                      </Typography>
                    </Stack>
                  </Stack>

                  <Box
                    sx={{
                      width: "100%",
                      height: 240,
                      bgcolor: "#000",
                      borderRadius: 1,
                      overflow: "hidden",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      position: "relative",
                    }}
                  >
                    {droneConnected ? (
                      <>
                        {videoError ? (
                          // Warning overlay when video fails
                          <Box
                            sx={{
                              width: "100%",
                              height: "100%",
                              display: "flex",
                              flexDirection: "column",
                              alignItems: "center",
                              justifyContent: "center",
                              bgcolor: "rgba(0,0,0,0.85)",
                              color: "warning.main",
                              p: 2,
                              textAlign: "center",
                            }}
                          >
                            <Typography variant="h6" sx={{ color: "warning.main", mb: 1 }}>
                              ⚠️ Video Stream Unavailable
                            </Typography>
                            <Typography variant="body2" sx={{ color: "grey.400", mb: 2 }}>
                              {videoError}
                            </Typography>
                            <Typography variant="caption" sx={{ color: "grey.500" }}>
                              Retry attempt {videoRetryCount}...
                            </Typography>
                            <Button
                              size="small"
                              variant="outlined"
                              sx={{ mt: 2, color: "white", borderColor: "grey.600" }}
                              onClick={() => {
                                setStreamKey(Date.now());
                                setVideoError(null);
                              }}
                            >
                              Retry Now
                            </Button>
                          </Box>
                        ) : (
                          <>
                            <Box
                              component="img"
                              src={`${API_BASE_CLEAN}/video/mjpeg?key=${streamKey}${videoToken ? `&token=${encodeURIComponent(videoToken)}` : ""}`}
                              alt="Survey camera stream"
                              onError={handleVideoError}
                              onLoad={handleVideoLoad}
                              sx={{ width: "100%", height: "100%", objectFit: "cover" }}
                            />

                            {/* Telemetry overlay boxes (like your screenshot) */}
                            <Box sx={{ position: "absolute", top: 8, left: 8 }}>
                              <Stack spacing={0.75}>
                                <TelemetryBox
                                  label="Battery"
                                  value={
                                    batteryPct === null
                                      ? "--"
                                      : `${formatMaybeNumber(Number(batteryPct), 0)}%`
                                  }
                                />
                                <TelemetryBox
                                  label="GND SPD"
                                  value={`${formatMaybeNumber(Number(groundSpeed), 1)} m/s`}
                                />
                                <TelemetryBox
                                  label="ALT"
                                  value={`${formatMaybeNumber(Number(relAlt), 1)} m`}
                                />
                              </Stack>
                            </Box>

                            <Box sx={{ position: "absolute", top: 8, right: 8 }}>
                              <Stack spacing={0.75} alignItems="flex-end">
                                <TelemetryBox
                                  label="MODE"
                                  value={typeof mode === "string" ? mode : "--"}
                                />
                                <TelemetryBox
                                  label="HDG"
                                  value={
                                    typeof heading === "number" && Number.isFinite(heading)
                                      ? `${Math.round(heading)}°`
                                      : "--"
                                  }
                                />
                                <TelemetryBox
                                  label="GPS"
                                  value={sats === null || sats === undefined ? "--" : `${sats} sats`}
                                />
                              </Stack>
                            </Box>
                          </>
                        )}

                        {startingVideo && (
                          <Box
                            sx={{
                              position: "absolute",
                              top: 0,
                              left: 0,
                              right: 0,
                              bottom: 0,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              backgroundColor: "rgba(0,0,0,0.7)",
                            }}
                          >
                            <CircularProgress />
                          </Box>
                        )}
                      </>
                    ) : (
                      <Typography sx={{ color: "white" }}>
                        Connect the drone to view the survey stream.
                      </Typography>
                    )}
                  </Box>
                </Paper>
              </Stack>

              {/* Right side: Controls */}
              <Box sx={{ width: { xs: "100%", md: 300 } }}>
                <Stack spacing={2}>
                  <Paper
                    variant="outlined"
                    sx={{
                      p: 2,
                      borderRadius: 2,
                      borderColor: "hsla(174, 30%, 40%, 0.25)",
                      background: "hsla(0, 0%, 100%, 0.7)",
                    }}
                  >
                    <Typography variant="subtitle1">Command Panel</Typography>
                    <Stack spacing={1.2} sx={{ mt: 1 }}>
                      <Stack direction="row" justifyContent="space-between" spacing={2}>
                        <Typography variant="body2" color="text.secondary">
                          Flight Status
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{ fontWeight: 600, color: failsafeActive ? "error.main" : "text.primary" }}
                        >
                          {flightStatus}
                        </Typography>
                      </Stack>
                      <Stack direction="row" justifyContent="space-between" spacing={2}>
                        <Typography variant="body2" color="text.secondary">
                          GPS Strength
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {gpsStrength}
                        </Typography>
                      </Stack>
                      <Stack direction="row" justifyContent="space-between" spacing={2}>
                        <Typography variant="body2" color="text.secondary">
                          Battery
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600, textAlign: "right" }}>
                          {batteryCellDisplay} • {batteryHealth}
                        </Typography>
                      </Stack>
                      <Stack direction="row" justifyContent="space-between" spacing={2}>
                        <Typography variant="body2" color="text.secondary">
                          Link Quality
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {linkQuality}
                        </Typography>
                      </Stack>
                      <Stack direction="row" justifyContent="space-between" spacing={2}>
                        <Typography variant="body2" color="text.secondary">
                          Wind @ Altitude
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {windDisplay}
                        </Typography>
                      </Stack>
                      <Stack direction="row" justifyContent="space-between" spacing={2}>
                        <Typography variant="body2" color="text.secondary">
                          Failsafe State
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{ fontWeight: 600, color: failsafeActive ? "error.main" : "text.primary" }}
                        >
                          {failsafeState}
                        </Typography>
                      </Stack>
                    </Stack>
                  </Paper>
                  <TextField
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
