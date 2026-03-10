import { useEffect, useRef, useState, useCallback, useMemo, useContext } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  IconButton,
  MenuItem,
  Paper,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import Header from "../../../components/dashboard/Header";
import InfoLabel from "../../../components/dashboard/InfoLabel";
import type { TerraDraw } from "terra-draw";
import {  Polyline,  Polygon,  OverlayView,} from "@react-google-maps/api";
import { getToken } from "../../../auth";
import DroneSvg from "../../../assets/Drone.svg?react";
import SvgIcon from "@mui/material/SvgIcon";
import RoomIcon from "@mui/icons-material/Room";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import { GoogleMapsContext } from "../../../utils/googleMaps";
import ChangeHistoryOutlinedIcon from "@mui/icons-material/ChangeHistoryOutlined";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import CropSquareOutlinedIcon from "@mui/icons-material/CropSquareOutlined";
import RadioButtonUncheckedOutlinedIcon from "@mui/icons-material/RadioButtonUncheckedOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import PanToolAltOutlinedIcon from "@mui/icons-material/PanToolAltOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import { CesiumViewControls } from "../../../components/dashboard/tasks/CesiumViewControls";
import { ErrorAlerts } from "../../../components/dashboard/tasks/ErrorAlerts";
import { MissionCommandPanel } from "../../../components/dashboard/tasks/MissionCommandPanel";
import { MissionPreflightPanel } from "../../../components/dashboard/tasks/MissionPreflightPanel";
import { MissionMapViewport } from "../../../components/dashboard/tasks/MissionMapViewport";
import { MissionVideoPanel } from "../../../components/dashboard/tasks/MissionVideoPanel";
import { MissionStatusChips } from "../../../components/dashboard/tasks/MissionStatusChips";
import { SavedFieldsPanel } from "../../../components/dashboard/tasks/SavedFieldsPanel";
import { FieldBorderPanel } from "../../../components/dashboard/tasks/FieldBorderPanel";
import {
  TerraDrawController,
  type TerraDrawEditorMode,
  type TerraDrawFeature,
  type TerraDrawToolMode,
} from "../../../components/dashboard/tasks/TerraDrawController";
import { useDroneCenter } from "../../../hooks/useDroneCenter";
import { useDroneMapFollow } from "../../../hooks/useDroneMapFollow";
import { useErrors } from "../../../hooks/useErrors";
import { useAutoStartVideo } from "../../../hooks/useAutoStartVideo";
import { useMissionCommandMetrics } from "../../../hooks/useMissionCommandMetrics";
import { useMissionWebsocketRuntime } from "../../../hooks/useMissionWebsocketRuntime";
import { type LatLng } from "../../../lib/extractLatLng";
import type { DrawResult as CesiumDrawResult } from "../../../utils/CesiumMap";
import {
  startMissionWithPreflight,
  type PreflightRunResponse,
} from "../../../utils/api";

type Waypoint = { lat: number; lon: number; alt: number };
type CesiumViewMode = "top" | "tilted" | "follow" | "fpv" | "orbit";
type DrawMode = "none" | "point" | "polyline" | "polygon";
type TerraFeature = TerraDrawFeature;
type LonLat = [number, number];
type PrivatePatrolTaskType =
  | "perimeter_patrol"
  | "waypoint_patrol"
  | "grid_surveillance"
  | "event_triggered_patrol";
type PatrolTriggerType =
  | "motion_sensor"
  | "fence_alarm"
  | "camera_detection"
  | "night_schedule"
  | "unknown_vehicle";
type PatrolAiTask =
  | "intruder_detection"
  | "vehicle_detection"
  | "fence_breach_detection"
  | "motion_detection";
type GridParams = {
  task_type: PrivatePatrolTaskType;
  path_offset_m: number;
  direction: "clockwise" | "counterclockwise";
  patrol_loops: number;
  speed_mps: number;
  camera_angle_deg: number;
  camera_overlap_pct: number;
  max_segment_length_m: number;
  hover_time_s: number;
  camera_scan_yaw_deg: number;
  zoom_capture: boolean;
  return_to_start: boolean;
  grid_spacing_m: number;
  grid_angle_deg: number;
  safety_inset_m: number;
  trigger_type: PatrolTriggerType;
  verification_loiter_s: number;
  verification_radius_m: number;
  track_target: boolean;
  auto_stream_video: boolean;
  target_label: string;
  ai_tasks: PatrolAiTask[];
};
type GridPreviewWaypoint = { lat: number; lon: number };
type GridPreviewStats = {
  task_type?: string;
  waypoints?: number;
  key_points?: number;
  rows?: number;
  perimeter_m?: number;
  total_route_m?: number;
  area_m2?: number;
  path_offset_requested_m?: number;
  path_offset_applied_m?: number;
  grid_spacing_m?: number;
  grid_angle_deg?: number;
  trigger_type?: string;
  trigger_action?: string;
  patrol_loops?: number;
  hover_time_s?: number;
  hover_total_s?: number;
  verification_loiter_s?: number;
  estimated_duration_s?: number;
};
type FieldSummary = {
  id: number;
  owner_id?: number;
  name: string;
  area_ha?: number | null;
};
type FieldFeature = FieldSummary & {
  ring: LonLat[];
  path: LatLng[];
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

type NoticeSeverity = "success" | "info" | "warning" | "error";
type UiNotice = {
  open: boolean;
  severity: NoticeSeverity;
  message: string;
};

const MAX_GRID_PREVIEW_WAYPOINTS = 2200;
const GRID_PREVIEW_DEBOUNCE_MS = 250;
const CESIUM_MAX_SAFE_ZOOM = 16;
const INFO_INPUT_LABEL_PROPS = {
  shrink: true,
  sx: { pointerEvents: "auto" },
} as const;

export default function PrivatePatrolPage() {
  const [fieldName, setFieldName] = useState("Field A");
  const [fieldBorder, setFieldBorder] = useState<LonLat[] | null>(null);
  const [fields, setFields] = useState<FieldFeature[]>([]);
  const [loadingFields, setLoadingFields] = useState(false);
  const [selectedFieldId, setSelectedFieldId] = useState<number | null>(null);
  const [fieldsRefreshNonce, setFieldsRefreshNonce] = useState(0);
  const [savingField, setSavingField] = useState(false);
  const [deletingField, setDeletingField] = useState(false);
  const [uiNotice, setUiNotice] = useState<UiNotice>({
    open: false,
    severity: "success",
    message: "",
  });
  const [pendingDeleteField, setPendingDeleteField] = useState<FieldFeature | null>(null);
  const containerStyle = { width: "100%", height: "400px" };
  const defaultCenter = { lat: 50.8503, lng: 4.3517 };
  const [drawMode, setDrawMode] = useState<DrawMode>("none");
  // TerraDraw refs and state
  const terraDrawRef = useRef<TerraDraw | null>(null);
  const [terraDrawReady, setTerraDrawReady] = useState(false);
  const [terraDrawMode, setTerraDrawMode] = useState<TerraDrawEditorMode>("static");

  const isTerraGuidanceFeature = useCallback((feature: TerraFeature): boolean => {
    const props = (feature?.properties ?? {}) as Record<string, unknown>;
    return Boolean(
      feature?.geometry?.type === "Point" &&
        (props.coordinatePoint ||
          props.closingPoint ||
          props.snappingPoint ||
          props.selectionPoint ||
          props.midPoint)
    );
  }, []);

  const isRemovableUserDrawingFeature = useCallback((feature: TerraFeature): boolean => {
    if (!feature || feature.id == null) return false;
    const mode =
      typeof feature?.properties?.mode === "string"
        ? feature.properties.mode
        : undefined;
    return mode !== "static" && !isTerraGuidanceFeature(feature);
  }, [isTerraGuidanceFeature]);

  const syncFieldBorderFromSnapshot = useCallback((snapshot: TerraFeature[]) => {
    const polygons = snapshot.filter(
      (f) =>
        isRemovableUserDrawingFeature(f) &&
        f?.geometry?.type === "Polygon" &&
        Array.isArray(
          ((f?.geometry as { coordinates?: unknown[] } | undefined)?.coordinates ??
            [])[0]
        )
    );

    if (polygons.length > 0) {
      const latest = polygons[polygons.length - 1];
      const coords = (latest.geometry?.coordinates as [number, number][][])[0];
      const ring: LonLat[] = coords.map(([lon, lat]) => [lon, lat]);
      setFieldBorder(ring);
      return;
    }

    // Allow saving a closed linestring as a field border as a fallback.
    const lines = snapshot.filter(
      (f) =>
        isRemovableUserDrawingFeature(f) &&
        f?.geometry?.type === "LineString" &&
        Array.isArray(f?.geometry?.coordinates)
    );
    if (lines.length > 0) {
      const latestLine = lines[lines.length - 1];
      const coords = latestLine.geometry?.coordinates as [number, number][];
      if (coords.length >= 3) {
        const ring: LonLat[] = coords.map(([lon, lat]) => [lon, lat]);
        setFieldBorder(ring);
        return;
      }
    }

    setFieldBorder(null);
  }, [isRemovableUserDrawingFeature]);

  const polygonPathToLonLat = useCallback((poly: google.maps.Polygon): LonLat[] => {
    const path = poly.getPath();
    const pts: LonLat[] = [];
    for (let i = 0; i < path.getLength(); i++) {
      const p = path.getAt(i);
      pts.push([p.lng(), p.lat()]);
    }
    return pts;
  }, []);

  const showUiNotice = useCallback((message: string, severity: NoticeSeverity = "success") => {
    setUiNotice({ open: true, severity, message });
  }, []);

  const handleUiNoticeClose = useCallback((_event?: unknown, reason?: string) => {
    if (reason === "clickaway") return;
    setUiNotice((prev) => ({ ...prev, open: false }));
  }, []);

  const clearFieldPolygonListeners = useCallback(() => {
    fieldPolygonListenersRef.current.forEach((listener) => {
      try {
        listener.remove();
      } catch {
        // ignore listener cleanup issues
      }
    });
    fieldPolygonListenersRef.current = [];
  }, []);

  const wirePolygonEditListeners = useCallback((poly: google.maps.Polygon) => {
    clearFieldPolygonListeners();
    const path = poly.getPath();

    const update = () => setFieldBorder(polygonPathToLonLat(poly));

    update();

    fieldPolygonListenersRef.current = [
      path.addListener("set_at", update),
      path.addListener("insert_at", update),
      path.addListener("remove_at", update),
    ];
  }, [clearFieldPolygonListeners, polygonPathToLonLat]);

  const clearFieldBorder = useCallback(() => {
    clearFieldPolygonListeners();
    if (fieldPolygonRef.current) {
      fieldPolygonRef.current.setMap(null);
      fieldPolygonRef.current = null;
    }
    // Clear only non-static user drawings; keep saved/static features.
    if (terraDrawRef.current) {
      try {
        const snapshot = terraDrawRef.current.getSnapshot();
        const idsToRemove = snapshot
          .filter((f) => isRemovableUserDrawingFeature(f))
          .map((f) => String(f.id));
        if (idsToRemove.length > 0) {
          terraDrawRef.current.removeFeatures(idsToRemove);
        }
      } catch {
        // ignore
      }
    }
    setFieldBorder(null);
    setSelectedFieldId(null);
  }, [clearFieldPolygonListeners, isRemovableUserDrawingFeature]);

  const saveFieldBorder = async () => {
    const token = getToken();
    if (!token) {
      addError("Not authenticated");
      return;
    }
    if (!fieldBorder || fieldBorder.length < 3) {
      addError("Draw a field polygon (min 3 points) before saving.");
      return;
    }
    if (!fieldName.trim()) {
      addError("Please enter a field name.");
      return;
    }
    setSavingField(true);
    try {
      const res = await fetch(`${API_BASE_CLEAN}/fields`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: fieldName.trim(),
          coordinates: fieldBorder,
          metadata: {},
        }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || "Failed to save field");
      }

      const data = await res.json();
      showUiNotice(`Saved field "${data.name}" (#${data.id})`);
      setFieldsRefreshNonce((n) => n + 1);
      setSelectedFieldId(data?.id ?? null);
    } catch (e: any) {
      addError(e?.message ?? "Failed to save field");
    } finally {
      setSavingField(false);
    }
  };

  const updateFieldBorder = async () => {
    const token = getToken();
    if (!token) {
      addError("Not authenticated");
      return;
    }
    if (selectedFieldId == null) {
      addError("Select a field to update.");
      return;
    }
    if (!fieldBorder || fieldBorder.length < 3) {
      addError("Draw/edit a field polygon (min 3 points) before updating.");
      return;
    }
    if (!fieldName.trim()) {
      addError("Please enter a field name.");
      return;
    }
    setSavingField(true);
    try {
      const res = await fetch(`${API_BASE_CLEAN}/fields/${selectedFieldId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: fieldName.trim(),
          coordinates: fieldBorder,
        }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || "Failed to update field");
      }

      const data = await res.json();
      showUiNotice(`Updated field "${data.name}" (#${data.id})`);
      setFieldsRefreshNonce((n) => n + 1);
    } catch (e: any) {
      addError(e?.message ?? "Failed to update field");
    } finally {
      setSavingField(false);
    }
  };

  const mapRef = useRef<google.maps.Map | null>(null);
  const fieldPolygonRef = useRef<google.maps.Polygon | null>(null);
  const fieldPolygonListenersRef = useRef<google.maps.MapsEventListener[]>([]);
  const missionLaunchInFlightRef = useRef(false);
  const gridPreviewAbortRef = useRef<AbortController | null>(null);
  const [userCenter, setUserCenter] = useState<LatLng | null>(null);
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const [eventLocation, setEventLocation] = useState<Waypoint | null>(null);
  const [alt, setAlt] = useState(30);
  const [altInput, setAltInput] = useState("30");
  const [name, setName] = useState("private-patrol-1");
  const [sending, setSending] = useState(false);
  const [preflightRun, setPreflightRun] =
    useState<PreflightRunResponse | null>(null);
  const [gridParams, setGridParams] = useState<GridParams>({
    task_type: "perimeter_patrol",
    path_offset_m: 15,
    direction: "clockwise",
    patrol_loops: 1,
    speed_mps: 6,
    camera_angle_deg: 35,
    camera_overlap_pct: 50,
    max_segment_length_m: 20,
    hover_time_s: 15,
    camera_scan_yaw_deg: 360,
    zoom_capture: true,
    return_to_start: true,
    grid_spacing_m: 40,
    grid_angle_deg: 0,
    safety_inset_m: 2,
    trigger_type: "fence_alarm",
    verification_loiter_s: 45,
    verification_radius_m: 18,
    track_target: true,
    auto_stream_video: true,
    target_label: "",
    ai_tasks: [
      "intruder_detection",
      "vehicle_detection",
      "fence_breach_detection",
      "motion_detection",
    ],
  });
  const [gridPreview, setGridPreview] = useState<GridPreviewWaypoint[] | null>(
    null
  );
  const [gridPreviewMask, setGridPreviewMask] = useState<boolean[] | null>(
    null
  );
  const [gridPreviewStats, setGridPreviewStats] = useState<GridPreviewStats | null>(
    null
  );
  const [gridPreviewError, setGridPreviewError] = useState<string | null>(null);
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
  const [previewLoading, setPreviewLoading] = useState(false);
  const [center, setCenter] = useState(defaultCenter);
  const [loadingLocation, setLoadingLocation] = useState(true);
  const { errors, addError, clearErrors, dismissError } = useErrors();
  const [exclusionZones, setExclusionZones] = useState<LonLat[][]>([]);
  const [fieldTilesetUrl, setFieldTilesetUrl] = useState<string | null>(null);
  const [mapZoom, setMapZoom] = useState(12);
  const [streamKey, setStreamKey] = useState(Date.now());
  const [mapReady, setMapReady] = useState(false);
  const videoToken = getToken();
  const waypointMarkersRef = useRef<any[]>([]);
  const [useCesium, setUseCesium] = useState(false);
  const [cesiumViewMode, setCesiumViewMode] = useState<CesiumViewMode>("tilted");
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY as string;
  const mapId = (import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string) || "";
  const API_BASE_RAW = import.meta.env.VITE_API_BASE_URL ?? "";
  const API_BASE_CLEAN = (API_BASE_RAW || "http://localhost:8000").replace(
    /\/$/,
    ""
  );
  const toAbsoluteAssetUrl = useCallback(
    (url: string) => {
      if (/^https?:\/\//i.test(url)) return url;
      return `${API_BASE_CLEAN}${url.startsWith("/") ? "" : "/"}${url}`;
    },
    [API_BASE_CLEAN]
  );
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

  const droneReady = Boolean(wsConnected && droneCenter);
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
    clearFieldPolygonListeners();
    if (fieldPolygonRef.current) {
      fieldPolygonRef.current.setMap(null);
      fieldPolygonRef.current = null;
    }
    mapRef.current = null;
    setMapReady(false);
  }, [clearFieldPolygonListeners]);

  const onMapZoomChanged = useCallback(() => {
    if (!mapRef.current) return;
    const zoom = mapRef.current.getZoom();
    if (typeof zoom === "number" && Number.isFinite(zoom)) {
      setMapZoom(zoom);
    }
  }, []);

  // Add this ref near your other refs (around line ~280)
  const lastSyncedCenterRef = useRef<LatLng | null>(null);

  // Replace the existing onMapCenterChanged with this:
  const onMapCenterChanged = useCallback(() => {
    if (!mapRef.current) return;

    const center = mapRef.current.getCenter();
    if (!center) return;

    const newCenter = { lat: center.lat(), lng: center.lng() };
    const last = lastSyncedCenterRef.current;

    // Only update if center changed significantly (> 0.00001° ≈ 1 meter)
    const hasChanged = !last ||
      Math.abs(last.lat - newCenter.lat) > 0.00001 ||
      Math.abs(last.lng - newCenter.lng) > 0.00001;

    if (hasChanged) {
      lastSyncedCenterRef.current = newCenter;
      setCenter(newCenter);
    }
  }, []);

  const selectedField = useMemo(
    () =>
      selectedFieldId == null
        ? null
        : fields.find((f) => f.id === selectedFieldId) ?? null,
    [fields, selectedFieldId]
  );

  const lonLatRingToPath = useCallback((ring: LonLat[]): LatLng[] => {
    return ring.map(([lon, lat]) => ({ lat, lng: lon }));
  }, []);

  const stripClosedRing = useCallback((ring: LonLat[]): LonLat[] => {
    if (ring.length >= 2) {
      const a = ring[0];
      const b = ring[ring.length - 1];
      if (a[0] === b[0] && a[1] === b[1]) return ring.slice(0, -1);
    }
    return ring;
  }, []);

  const computeCentroid = useCallback(
    (ring: LonLat[]): LatLng | null => {
      const pts = stripClosedRing(ring);
      if (pts.length < 3) return null;
      let twiceArea = 0;
      let cx = 0;
      let cy = 0;

      for (let i = 0; i < pts.length; i++) {
        const [x0, y0] = pts[i];
        const [x1, y1] = pts[(i + 1) % pts.length];
        const f = x0 * y1 - x1 * y0;
        twiceArea += f;
        cx += (x0 + x1) * f;
        cy += (y0 + y1) * f;
      }

      if (Math.abs(twiceArea) < 1e-12) {
        const avg = pts.reduce(
          (acc, [x, y]) => ({ x: acc.x + x, y: acc.y + y }),
          { x: 0, y: 0 }
        );
        return { lng: avg.x / pts.length, lat: avg.y / pts.length };
      }

      const area6 = twiceArea * 3;
      return { lng: cx / area6, lat: cy / area6 };
    },
    [stripClosedRing]
  );

  const computeAreaHa = useCallback(
    (ring: LonLat[]): number | null => {
      const pts = stripClosedRing(ring);
      if (pts.length < 3) return null;
      if (!(window as any).google?.maps?.geometry?.spherical) return null;
      const latLngs = pts.map(([lon, lat]) => new google.maps.LatLng(lat, lon));
      const m2 = google.maps.geometry.spherical.computeArea(latLngs);
      return m2 / 10000;
    },
    [stripClosedRing]
  );

  const loadRingIntoEditor = useCallback(
    (ring: LonLat[]) => {
      if (!mapRef.current || !(window as any).google?.maps) return;

      clearFieldPolygonListeners();
      if (fieldPolygonRef.current) {
        fieldPolygonRef.current.setMap(null);
        fieldPolygonRef.current = null;
      }

      const pts = stripClosedRing(ring);

      const poly = new google.maps.Polygon({
        paths: pts.map(([lon, lat]) => ({ lat, lng: lon })),
        editable: true,
        draggable: false,
        fillColor: "#000000",
        fillOpacity: 0,
        strokeOpacity: 0.9,
        strokeWeight: 2,
        zIndex: 20,
      });

      poly.setMap(mapRef.current);
      fieldPolygonRef.current = poly;
      wirePolygonEditListeners(poly);
    },
    [clearFieldPolygonListeners, stripClosedRing, wirePolygonEditListeners]
  );

  const focusRingOnMap = useCallback(
    (ring: LonLat[]) => {
      if (!mapRef.current || !(window as any).google?.maps || ring.length < 3) return;

      const pts = stripClosedRing(ring);
      const bounds = new google.maps.LatLngBounds();
      pts.forEach(([lon, lat]) => bounds.extend({ lat, lng: lon }));

      if (!bounds.isEmpty()) {
        mapRef.current.fitBounds(bounds);
      }
    },
    [stripClosedRing]
  );

  const fetchFields = useCallback(async () => {
    setLoadingFields(true);
    try {
      const token = getToken();
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`${API_BASE_CLEAN}/fields/features`, {
        headers,
      });
      if (!res.ok)
        throw new Error((await res.text()) || "Failed to fetch fields");
      const fc = await res.json();

      const features: FieldFeature[] = [];
      for (const feat of fc.features ?? []) {
        const props = feat.properties ?? {};
        const coords: LonLat[] | undefined = feat?.geometry?.coordinates?.[0];
        if (!coords || coords.length < 4) continue;
        const ring = stripClosedRing(coords);
        features.push({
          id: props.id,
          owner_id: props.owner_id,
          name: props.name,
          area_ha: props.area_ha ?? null,
          ring,
          path: lonLatRingToPath(ring),
        });
      }

      features.sort((a, b) => b.id - a.id);
      setFields(features);
    } catch (e: any) {
      addError(e?.message ?? "Failed to load fields");
    } finally {
      setLoadingFields(false);
    }
  }, [API_BASE_CLEAN, addError, lonLatRingToPath, stripClosedRing]);

  useEffect(() => {
    fetchFields();
  }, [fetchFields, fieldsRefreshNonce]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(`${API_BASE_CLEAN}/geofences?active=true&limit=200`);
        if (!res.ok) return;
        const geofences = await res.json();
        const zones: LonLat[][] = [];

        await Promise.all(
          (geofences ?? []).map(async (g: any) => {
            const id = g?.id;
            if (typeof id !== "number") return;
            const detailRes = await fetch(`${API_BASE_CLEAN}/geofences/${id}/geojson`);
            if (!detailRes.ok) return;
            const feature = await detailRes.json();
            const ring: LonLat[] | undefined = feature?.geometry?.coordinates?.[0];
            if (Array.isArray(ring) && ring.length >= 4) {
              zones.push(stripClosedRing(ring));
            }
          })
        );

        if (!cancelled) setExclusionZones(zones);
      } catch {
        if (!cancelled) setExclusionZones([]);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [API_BASE_CLEAN, stripClosedRing]);

  useEffect(() => {
    let cancelled = false;

    const fieldId = selectedFieldId;
    if (fieldId == null) {
      setFieldTilesetUrl(null);
      return;
    }

    const token = getToken();
    if (!token) {
      setFieldTilesetUrl(null);
      return;
    }

    (async () => {
      try {
        const res = await fetch(`${API_BASE_CLEAN}/mapping/fields/${fieldId}/latest-ready`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          if (!cancelled) setFieldTilesetUrl(null);
          return;
        }

        const payload = await res.json();
        const assets = Array.isArray(payload?.assets) ? payload.assets : [];
        const tilesetAsset = assets.find((a: any) => a?.type === "TILESET_3D");
        const rawUrl = typeof tilesetAsset?.url === "string" ? tilesetAsset.url : "";
        if (!cancelled) {
          setFieldTilesetUrl(rawUrl ? toAbsoluteAssetUrl(rawUrl) : null);
        }
      } catch {
        if (!cancelled) setFieldTilesetUrl(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [API_BASE_CLEAN, selectedFieldId, toAbsoluteAssetUrl]);

  const selectField = useCallback(
    (f: FieldFeature) => {
      setUseCesium(false);
      setSelectedFieldId(f.id);
      setFieldName(f.name);
      setFieldBorder(f.ring);
      loadRingIntoEditor(f.ring);
      focusRingOnMap(f.ring);
    },
    [focusRingOnMap, loadRingIntoEditor]
  );

  const handleSavedFieldSelect = useCallback(
    (fieldId: number | null) => {
      if (fieldId == null) {
        clearFieldBorder();
        return;
      }
      const field = fields.find((f) => f.id === fieldId);
      if (field) selectField(field);
    },
    [clearFieldBorder, fields, selectField]
  );

  const handleNewField = useCallback(() => {
    setSelectedFieldId(null);
    setFieldName("Field A");
    clearFieldBorder();
  }, [clearFieldBorder]);

  const requestDeleteSelectedField = useCallback(() => {
    const token = getToken();
    if (!token) {
      addError("Not authenticated");
      return;
    }
    if (!selectedFieldId) {
      addError("Select a saved field to delete.");
      return;
    }

    const targetField = fields.find((f) => f.id === selectedFieldId) ?? null;
    if (!targetField) {
      addError("Selected field could not be resolved.");
      return;
    }
    setPendingDeleteField(targetField);
  }, [addError, fields, selectedFieldId]);

  const closeDeleteFieldDialog = useCallback(() => {
    if (deletingField) return;
    setPendingDeleteField(null);
  }, [deletingField]);

  const confirmDeleteSelectedField = useCallback(async () => {
    const token = getToken();
    if (!token) {
      addError("Not authenticated");
      return;
    }
    if (!pendingDeleteField) {
      return;
    }

    setDeletingField(true);
    try {
      const res = await fetch(`${API_BASE_CLEAN}/fields/${pendingDeleteField.id}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || "Failed to delete field");
      }

      setFields((prev) => prev.filter((f) => f.id !== pendingDeleteField.id));
      clearFieldBorder();
      setFieldName("Field A");
      setPendingDeleteField(null);
      showUiNotice(`Deleted field "${pendingDeleteField.name}"`);
    } catch (e: any) {
      addError(e?.message ?? "Failed to delete field");
    } finally {
      setDeletingField(false);
    }
  }, [API_BASE_CLEAN, addError, clearFieldBorder, pendingDeleteField, showUiNotice]);

  useEffect(() => {
    if (useCesium) return;
    if (!mapReady || !selectedField) return;
    loadRingIntoEditor(selectedField.ring);
    focusRingOnMap(selectedField.ring);
  }, [
    focusRingOnMap,
    loadRingIntoEditor,
    mapReady,
    selectedField,
    useCesium,
  ]);

  const metrics = useMemo(() => {
    if (!fieldBorder || fieldBorder.length < 3) return null;
    const areaHa = computeAreaHa(fieldBorder);
    const centroid = computeCentroid(fieldBorder);
    return { areaHa, centroid };
  }, [computeAreaHa, computeCentroid, fieldBorder]);

  const gridPreviewTooDense =
    !!gridPreview && gridPreview.length > MAX_GRID_PREVIEW_WAYPOINTS;

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
      }
    );
  }, [addError]);

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

  useEffect(() => {
    if (!isLoaded || !mapReady) return;
    if (!mapRef.current) return;
    const markerLib = (google.maps as any)?.marker;
    if (!markerLib?.AdvancedMarkerElement) {
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

    if (terraDrawMode !== "static") return;

    const markersToRender: Array<{ point: Waypoint; title: string; color: string }> = [];
    if (gridParams.task_type === "waypoint_patrol" && waypoints.length > 0) {
      waypoints.forEach((p) =>
        markersToRender.push({ point: p, title: "Waypoint", color: "#1976d2" })
      );
    } else if (gridParams.task_type === "event_triggered_patrol" && eventLocation) {
      markersToRender.push({
        point: eventLocation,
        title: "Event Location",
        color: "#d32f2f",
      });
    }
    if (markersToRender.length === 0) return;

    markersToRender.forEach(({ point, title, color }) => {
      const content = document.createElement("div");
      content.style.width = "12px";
      content.style.height = "12px";
      content.style.borderRadius = "50%";
      content.style.background = color;
      content.style.border = "2px solid #ffffff";
      content.style.boxShadow = "0 2px 6px rgba(0,0,0,0.2)";

      const marker = new markerLib.AdvancedMarkerElement({
        map: mapRef.current,
        position: { lat: point.lat, lng: point.lon },
        content,
        title,
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
  }, [eventLocation, gridParams.task_type, isLoaded, mapReady, terraDrawMode, waypoints]);

useEffect(() => {
  if (useCesium) return;

  const modeMap: Record<DrawMode, TerraDrawEditorMode> = {
    polygon: "polygon",
    polyline: "linestring",
    point: "point",
    none: "static",
  };

  const tdMode = modeMap[drawMode];
  if (tdMode) setTerraDrawMode(tdMode);
}, [drawMode, useCesium]);

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
      if (terraDrawMode !== "static") return;
      if (!e.latLng) return;
      const lat = e.latLng.lat();
      const lng = e.latLng.lng();
      if (gridParams.task_type === "waypoint_patrol") {
        setWaypoints((prev) => [...prev, { lat, lon: lng, alt }]);
        return;
      }
      if (gridParams.task_type === "event_triggered_patrol") {
        setEventLocation({ lat, lon: lng, alt });
      }
    },
    [alt, gridParams.task_type, terraDrawMode]
  );
  const handleDrawingToolSelection = useCallback(
    (toolMode: TerraDrawToolMode) => {
      if (useCesium) {
        const cesiumModeMap: Record<TerraDrawToolMode, DrawMode> = {
          polygon: "polygon",
          linestring: "polyline",
          point: "point",
          rectangle: "polygon",
          circle: "polygon",
          freehand: "polygon",
          select: "none",
        };
        setDrawMode(cesiumModeMap[toolMode] ?? "none");
        return;
      }

      setTerraDrawMode(toolMode);
    },
    [useCesium]
  );
  const handleCesiumDrawComplete = useCallback(
    (result: CesiumDrawResult) => {
      if (result.type === "polygon") {
        const ring = stripClosedRing(
          result.coordinates.map(([lon, lat]) => [lon, lat] as LonLat)
        );
        if (ring.length >= 3) {
          setFieldBorder(ring);
          setSelectedFieldId(null);
        }
      } else if (result.type === "polyline") {
        if (gridParams.task_type === "waypoint_patrol") {
          setWaypoints(
            result.coordinates.map(([lon, lat]) => ({
              lat,
              lon,
              alt,
            }))
          );
        }
      } else if (result.type === "point") {
        if (gridParams.task_type === "waypoint_patrol") {
          const [lon, lat] = result.coordinates;
          setWaypoints((prev) => [...prev, { lat, lon, alt }]);
        } else if (gridParams.task_type === "event_triggered_patrol") {
          const [lon, lat] = result.coordinates;
          setEventLocation({ lat, lon, alt });
        }
      }

      setDrawMode("none");
    },
    [alt, gridParams.task_type, stripClosedRing]
  );

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

  const fetchGridPreview = useCallback(
    async (signal: AbortSignal) => {
      if (!useCesium && terraDrawMode !== "static" && terraDrawMode !== "select") {
        setPreviewLoading(false);
        return;
      }
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
        setGridPreview(null);
        setGridPreviewMask(null);
        setGridPreviewStats(null);
        setGridPreviewError(null);
        setPreviewLoading(false);
        return;
      }
      const token = getToken();
      if (!token) return;
      setPreviewLoading(true);
      try {
        const res = await fetch(`${API_BASE_CLEAN}/tasks/missions/private-patrol/preview`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          signal,
          body: JSON.stringify({
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
          }),
        });
        if (!res.ok) {
          const raw = await res.text();
          let detail = raw;
          try {
            const parsed = JSON.parse(raw);
            if (parsed?.detail) detail = String(parsed.detail);
          } catch {
            // keep raw text fallback
          }
          setGridPreview(null);
          setGridPreviewMask(null);
          setGridPreviewStats(null);
          setGridPreviewError(detail || `Patrol preview failed (HTTP ${res.status})`);
          return;
        }
        const data = await res.json();
        if (signal.aborted) return;
        setGridPreview(data.waypoints);
        setGridPreviewMask(data.work_leg_mask);
        setGridPreviewStats(data.stats ?? null);
        setGridPreviewError(null);
      } catch {
        if (signal.aborted) return;
        setGridPreview(null);
        setGridPreviewMask(null);
        setGridPreviewStats(null);
        setGridPreviewError("Patrol preview failed. Please try again.");
      } finally {
        if (!signal.aborted) setPreviewLoading(false);
      }
    },
    [API_BASE_CLEAN, alt, eventLocation, fieldBorder, gridParams, terraDrawMode, useCesium, waypoints]
  );

  useEffect(() => {
    if (gridPreviewAbortRef.current) {
      gridPreviewAbortRef.current.abort();
    }
    const controller = new AbortController();
    gridPreviewAbortRef.current = controller;
    const timer = setTimeout(() => {
      void fetchGridPreview(controller.signal);
    }, GRID_PREVIEW_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
      if (gridPreviewAbortRef.current === controller) {
        gridPreviewAbortRef.current = null;
      }
    };
  }, [fetchGridPreview]);

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

      const { preflight, mission: data } = await startMissionWithPreflight(
        payload,
        token,
        API_BASE_CLEAN,
      );
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
  const cesiumFieldBoundary = useMemo(
    () => (fieldBorder && fieldBorder.length >= 3 ? fieldBorder : null),
    [fieldBorder]
  );
  const cesiumPlannedRoute = useMemo(() => {
    if (gridPreview && gridPreview.length >= 2) {
      return gridPreview.map((p) => [p.lon, p.lat] as LonLat);
    }
    if (isWaypointPatrol && waypoints.length >= 2) {
      return waypoints.map((p) => [p.lon, p.lat] as LonLat);
    }
    return null;
  }, [gridPreview, isWaypointPatrol, waypoints]);

  const mapCenter = useMemo(() => userCenter || center, [userCenter, center]);
  const cesiumZoom = useMemo(
    () => Math.min(mapZoom, CESIUM_MAX_SAFE_ZOOM),
    [mapZoom]
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
          <div>
            <Typography variant="h5">Private Patrol</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Persistent surveillance missions for private property security with
              perimeter patrol, key-point verification, grid area coverage, and
              event-triggered response workflows.
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
            Missing Google Maps API Key. Please set
            VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY in your .env file.
          </Alert>
        ) : loadError ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load Google Maps. {loadError.message} Ensure the Maps
            JavaScript API is enabled, billing is active, and the key allows
            your domain.
          </Alert>
        ) : !mapId ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Google Maps Map ID is not set. Advanced markers require a Map ID.
            Set VITE_GOOGLE_MAPS_MAP_ID to remove this warning.
          </Alert>
        ) : (
          <>
            <TerraDrawController
              map={mapReady ? mapRef.current : null}
              enabled={!useCesium}
              mode={terraDrawMode}
              drawRef={terraDrawRef}
              onReadyChange={setTerraDrawReady}
              onSnapshotChange={syncFieldBorderFromSnapshot}
              onError={addError}
            />
            <Stack
              direction={{ xs: "column", md: "row" }}
              spacing={3}
              sx={{ mb: 3 }}
            >
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
                      onUnmount: onMapUnmount,
                      onZoomChanged: onMapZoomChanged,
                      onCenterChanged: onMapCenterChanged,
                      options: mapOptions,
                    }}
                    cesiumMapProps={{
                      center: mapCenter,
                      zoom: cesiumZoom,
                      viewMode: cesiumViewMode,
                      waypoints,
                      fieldBoundary: cesiumFieldBoundary,
                      plannedRoute: cesiumPlannedRoute,
                      exclusionZones,
                      fieldTilesetUrl,
                      droneCenter,
                      headingDeg: typeof heading === "number" ? heading : null,
                      onPickLatLng: handleCesiumPick,
                      drawMode,
                      onDrawComplete: handleCesiumDrawComplete,
                    }}
                    googleWrapperSx={{ position: "relative" }}
                    googleChildren={
                      <>
                        {fields.map((f) => (
                          <Polygon
                            key={f.id}
                            paths={f.path}
                            onClick={() => selectField(f)}
                            options={{
                              clickable: true,
                              fillColor: "#000000",
                              fillOpacity: 0,
                              strokeOpacity: 0.85,
                              strokeWeight: selectedFieldId === f.id ? 3 : 2,
                              zIndex: selectedFieldId === f.id ? 15 : 5,
                            }}
                          />
                        ))}

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

                        {isEventTriggeredPatrol && eventLocation && (
                          <OverlayView
                            position={{ lat: eventLocation.lat, lng: eventLocation.lon }}
                            mapPaneName={OverlayView.OVERLAY_LAYER}
                          >
                            <div
                              style={{
                                transform: "translate(-50%, -50%)",
                                color: "#d32f2f",
                              }}
                            >
                              <PlaceOutlinedIcon fontSize="large" />
                            </div>
                          </OverlayView>
                        )}

                        {gridPreview && gridPreview.length >= 2 && (
                          <>
                            {gridPreviewPolylineGroups.work.map((path, i) => (
                              <Polyline
                                key={`work-${i}`}
                                path={path}
                                options={{
                                  strokeColor: "#2e7d32",
                                  strokeOpacity: 0.85,
                                  strokeWeight: 2,
                                }}
                              />
                            ))}
                            {gridPreviewPolylineGroups.turn.map((path, i) => (
                              <Polyline
                                key={`turn-${i}`}
                                path={path}
                                options={{
                                  strokeColor: "#f57c00",
                                  strokeOpacity: 0.6,
                                  strokeWeight: 1.5,
                                  icons: [
                                    {
                                      icon: {
                                        path: "M 0,-1 0,1",
                                        strokeOpacity: 1,
                                        scale: 2,
                                      },
                                      offset: "0",
                                      repeat: "10px",
                                    },
                                  ],
                                }}
                              />
                            ))}
                          </>
                        )}

                        {isWaypointPatrol && terraDrawMode === "static" && waypoints.length >= 2 && (
                          <Polyline
                            path={polylinePath}
                            options={{
                              strokeColor: "#1976d2",
                              strokeOpacity: 0.8,
                              strokeWeight: 3,
                            }}
                          />
                        )}
                      </>
                    }
                    googleOverlay={
                      <Paper
                        elevation={2}
                        sx={{
                          position: "absolute",
                          left: 10,
                          top: "50%",
                          transform: "translateY(-50%)",
                          zIndex: 1300,
                          pointerEvents: "auto",
                          p: 0.5,
                          borderRadius: 1.5,
                          border: "1px solid",
                          borderColor: "divider",
                          bgcolor: "rgba(255,255,255,0.92)",
                          backdropFilter: "blur(2px)",
                        }}
                      >
                        <Stack direction="column" spacing={0.5}>
                          {[
                            {
                              mode: "polygon",
                              label: "Polygon",
                              icon: <ChangeHistoryOutlinedIcon fontSize="small" />,
                            },
                            {
                              mode: "linestring",
                              label: "Line",
                              icon: <ShowChartIcon fontSize="small" />,
                            },
                            {
                              mode: "point",
                              label: "Point",
                              icon: <PlaceOutlinedIcon fontSize="small" />,
                            },
                            {
                              mode: "rectangle",
                              label: "Rectangle",
                              icon: <CropSquareOutlinedIcon fontSize="small" />,
                            },
                            {
                              mode: "circle",
                              label: "Circle",
                              icon: <RadioButtonUncheckedOutlinedIcon fontSize="small" />,
                            },
                            {
                              mode: "freehand",
                              label: "Freehand",
                              icon: <EditOutlinedIcon fontSize="small" />,
                            },
                            {
                              mode: "select",
                              label: "Select",
                              icon: <PanToolAltOutlinedIcon fontSize="small" />,
                            },
                          ].map((tool) => {
                            const selected = useCesium
                              ? (drawMode === "point" && tool.mode === "point") ||
                                (drawMode === "polyline" && tool.mode === "linestring") ||
                                (drawMode === "polygon" &&
                                  ["polygon", "rectangle", "circle", "freehand"].includes(
                                    tool.mode
                                  )) ||
                                (drawMode === "none" && tool.mode === "select")
                              : terraDrawMode === tool.mode;
                            return (
                              <Tooltip key={tool.mode} title={tool.label} placement="right" arrow>
                                <span>
                                  <IconButton
                                    size="small"
                                    onClick={() =>
                                      handleDrawingToolSelection(
                                        tool.mode as TerraDrawToolMode
                                      )
                                    }
                                    sx={{
                                      border: "1px solid",
                                      borderColor: "divider",
                                      bgcolor: selected ? "primary.main" : "background.paper",
                                      color: selected
                                        ? "primary.contrastText"
                                        : "text.primary",
                                      "&:hover": {
                                        bgcolor: selected
                                          ? "primary.dark"
                                          : "action.hover",
                                      },
                                    }}
                                  >
                                    {tool.icon}
                                  </IconButton>
                                </span>
                              </Tooltip>
                            );
                          })}

                          <Tooltip title="Delete latest drawing" placement="right" arrow>
                            <span>
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => {
                                  if (useCesium) {
                                    if (drawMode !== "none") {
                                      setDrawMode("none");
                                      return;
                                    }
                                    if (isEventTriggeredPatrol && eventLocation) {
                                      setEventLocation(null);
                                      return;
                                    }
                                    if (isWaypointPatrol && waypoints.length > 0) {
                                      setWaypoints((prev) => prev.slice(0, -1));
                                      return;
                                    }
                                    if (fieldBorder && fieldBorder.length > 0) {
                                      setFieldBorder((prev) => {
                                        if (!prev || prev.length <= 1) return null;
                                        return prev.slice(0, -1) as LonLat[];
                                      });
                                      return;
                                    }
                                    return;
                                  }

                                  if (isEventTriggeredPatrol && eventLocation) {
                                    setEventLocation(null);
                                    return;
                                  }
                                  if (isWaypointPatrol && waypoints.length > 0) {
                                    setWaypoints((prev) => prev.slice(0, -1));
                                    return;
                                  }
                                  if (!terraDrawRef.current) return;
                                  const snapshot = terraDrawRef.current.getSnapshot();
                                  const latestFeature = [...snapshot]
                                    .reverse()
                                    .find((f) => isRemovableUserDrawingFeature(f));
                                  if (!latestFeature) return;

                                  terraDrawRef.current.removeFeatures([
                                    String(latestFeature.id),
                                  ]);

                                  const remaining = terraDrawRef.current.getSnapshot();
                                  syncFieldBorderFromSnapshot(remaining);
                                }}
                                disabled={
                                  useCesium
                                    ? drawMode === "none" &&
                                      (!fieldBorder || fieldBorder.length === 0) &&
                                      waypoints.length === 0 &&
                                      !eventLocation
                                    : !terraDrawReady
                                }
                                sx={{
                                  border: "1px solid",
                                  borderColor: "divider",
                                  bgcolor: "background.paper",
                                  "&:hover": { bgcolor: "action.hover" },
                                }}
                              >
                                <DeleteOutlineOutlinedIcon fontSize="small" />
                              </IconButton>
                            </span>
                          </Tooltip>
                        </Stack>
                      </Paper>
                    }
                  />
                </Box>

                <Paper
                                    variant="outlined"
                                    sx={{
                                      p: 1.5,
                                      borderRadius: 2,
                                      flexShrink: 0,
                                      alignSelf: { xs: "stretch", lg: "flex-start" },
                                    }}
                                  >

                                    <CesiumViewControls
                                      useCesium={useCesium}
                                      onUseCesiumChange={setUseCesium}
                                      viewMode={cesiumViewMode}
                                      onViewModeChange={setCesiumViewMode}
                                    />
                                  </Paper>

                <Box
                  sx={{
                    mt: 1,
                    display: "grid",
                    gridTemplateColumns: {
                      xs: "1fr",
                      lg: "minmax(280px, 0.9fr) minmax(0, 1.6fr)",
                    },
                    gap: 2,
                  }}
                >
                  <SavedFieldsPanel
                    fields={fields}
                    selectedFieldId={selectedFieldId}
                    selectedField={selectedField}
                    loadingFields={loadingFields}
                    deletingField={deletingField}
                    onSelectField={handleSavedFieldSelect}
                    onRefresh={() => setFieldsRefreshNonce((n) => n + 1)}
                    onFocusSelected={() => selectedField && focusRingOnMap(selectedField.ring)}
                    onDeleteSelected={requestDeleteSelectedField}
                  />

                  <Stack
                    direction={{ xs: "column", lg: "row" }}
                    spacing={1}
                    alignItems={{ xs: "stretch", lg: "flex-start" }}
                  >
                    <FieldBorderPanel
                      fieldName={fieldName}
                      selectedFieldId={selectedFieldId}
                      fieldBorder={fieldBorder}
                      metrics={metrics}
                      selectedFieldDisplayId={selectedField?.id ?? null}
                      savingField={savingField}
                      onFieldNameChange={setFieldName}
                      onSaveOrUpdate={
                        selectedFieldId ? updateFieldBorder : saveFieldBorder
                      }
                      onClearBorder={clearFieldBorder}
                      onNewField={handleNewField}
                    />
                  </Stack>
                </Box>

                <Box sx={{ mt: 3 }}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Private Patrol Parameters
                  </Typography>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
                    <Box
                      sx={{
                        display: "grid",
                        gridTemplateColumns: {
                          xs: "1fr",
                          md: "repeat(2, minmax(0, 1fr))",
                          xl: "repeat(3, minmax(0, 1fr))",
                        },
                        gap: 1.5,
                        alignItems: "start",
                      }}
                    >
                      <TextField
                        variant="filled"
                        select
                        label={
                          <InfoLabel
                            label="Mission task"
                            info="Task profile for private property security missions."
                          />
                        }
                        InputLabelProps={INFO_INPUT_LABEL_PROPS}
                        size="small"
                        fullWidth
                        value={gridParams.task_type}
                        onChange={(e) =>
                          setGridParams((p) => ({
                            ...p,
                            task_type: e.target.value as GridParams["task_type"],
                          }))
                        }
                      >
                          <MenuItem value="perimeter_patrol">A. Perimeter Patrol Mission</MenuItem>
                          <MenuItem value="waypoint_patrol">B. Waypoint Patrol (Key Points)</MenuItem>
                          <MenuItem value="grid_surveillance">C. Grid Surveillance Mission</MenuItem>
                          <MenuItem value="event_triggered_patrol">
                            D. Event-Triggered Patrol
                          </MenuItem>
                        </TextField>
                      <TextField
                        variant="filled"
                        label={
                          <InfoLabel
                            label="Speed (m/s)"
                            info={
                              isWaypointPatrol
                                ? "Waypoint patrol uses moderate speed for precise checkpoint approaches."
                                : isGridSurveillance
                                  ? "Typical grid surveillance speed is 4–6 m/s for stable area coverage."
                                  : isEventTriggeredPatrol
                                    ? "Event response missions prioritize rapid verification (typically 5-8 m/s)."
                                  : "Typical perimeter patrol speed is 5–8 m/s."
                            }
                          />
                        }
                        InputLabelProps={INFO_INPUT_LABEL_PROPS}
                        type="number"
                        size="small"
                        fullWidth
                        value={gridParams.speed_mps}
                        onChange={(e) => {
                          const value = Number(e.target.value);
                          if (!Number.isFinite(value)) return;
                          setGridParams((p) => ({
                            ...p,
                            speed_mps: Math.min(20, Math.max(0.5, value)),
                          }));
                        }}
                        inputProps={{ min: 0.5, max: 20, step: 0.1 }}
                      />
                      {gridParams.task_type === "perimeter_patrol" && (
                        <>
                          <TextField
                            variant="filled"
                            select
                            label={
                              <InfoLabel
                                label="Direction"
                                info="Drone route direction around the perimeter."
                              />
                            }
                            InputLabelProps={INFO_INPUT_LABEL_PROPS}
                            size="small"
                            fullWidth
                            value={gridParams.direction}
                            onChange={(e) =>
                              setGridParams((p) => ({
                                ...p,
                                direction: e.target.value as GridParams["direction"],
                              }))
                            }
                          >
                            <MenuItem value="clockwise">Clockwise</MenuItem>
                            <MenuItem value="counterclockwise">Counter-clockwise</MenuItem>
                          </TextField>
                          <TextField
                            variant="filled"
                            label={
                              <InfoLabel
                                label="Perimeter offset (m)"
                                info="Typical private patrol offset is 10–30m from the property boundary."
                              />
                            }
                            InputLabelProps={INFO_INPUT_LABEL_PROPS}
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.path_offset_m}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                path_offset_m: Math.max(0, value),
                              }));
                            }}
                            inputProps={{ min: 0, max: 120, step: 1 }}
                          />
                          <TextField
                            variant="filled"
                            label="Patrol loops"
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.patrol_loops}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                patrol_loops: Math.min(200, Math.max(1, Math.round(value))),
                              }));
                            }}
                            inputProps={{ min: 1, max: 200, step: 1 }}
                          />
                          <TextField
                            variant="filled"
                            label={
                              <InfoLabel
                                label="Camera angle (° down)"
                                info="Typical private patrol camera tilt is 30–45° downward."
                              />
                            }
                            InputLabelProps={INFO_INPUT_LABEL_PROPS}
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.camera_angle_deg}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                camera_angle_deg: Math.min(90, Math.max(0, value)),
                              }));
                            }}
                            inputProps={{ min: 0, max: 90, step: 1 }}
                          />
                          <TextField
                            variant="filled"
                            label={
                              <InfoLabel
                                label="Camera overlap (%)"
                                info="Typical overlap for patrol verification imagery is 40–60%."
                              />
                            }
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.camera_overlap_pct}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                camera_overlap_pct: Math.min(95, Math.max(0, value)),
                              }));
                            }}
                            inputProps={{ min: 0, max: 95, step: 1 }}
                          />
                          <TextField
                            variant="filled"
                            label={
                              <InfoLabel
                                label="Max segment length (m)"
                                info="Smaller segments create smoother perimeter tracking."
                              />
                            }
                            InputLabelProps={INFO_INPUT_LABEL_PROPS}
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.max_segment_length_m}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                max_segment_length_m: Math.min(300, Math.max(2, value)),
                              }));
                            }}
                            inputProps={{ min: 2, max: 300, step: 1 }}
                          />
                        </>
                      )}
                      {gridParams.task_type === "waypoint_patrol" && (
                        <>
                          <TextField
                            variant="filled"
                            label={
                              <InfoLabel
                                label="Hover time (s)"
                                info="Hold 10-20 seconds at each key checkpoint for verification."
                              />
                            }
                            InputLabelProps={INFO_INPUT_LABEL_PROPS}
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.hover_time_s}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                hover_time_s: Math.min(300, Math.max(1, value)),
                              }));
                            }}
                            inputProps={{ min: 1, max: 300, step: 1 }}
                          />
                          <TextField
                            variant="filled"
                            label={
                              <InfoLabel
                                label="Camera scan yaw (°)"
                                info="Set to 360° for full panorama scan at each key point."
                              />
                            }
                            InputLabelProps={INFO_INPUT_LABEL_PROPS}
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.camera_scan_yaw_deg}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                camera_scan_yaw_deg: Math.min(360, Math.max(0, value)),
                              }));
                            }}
                            inputProps={{ min: 0, max: 360, step: 5 }}
                          />
                          <FormControlLabel
                            control={
                              <Switch
                                size="small"
                                checked={gridParams.zoom_capture}
                                onChange={(e) =>
                                  setGridParams((p) => ({
                                    ...p,
                                    zoom_capture: e.target.checked,
                                  }))
                                }
                              />
                            }
                            label={
                              <Typography variant="body2">Zoom capture at checkpoints</Typography>
                            }
                          />
                          <FormControlLabel
                            control={
                              <Switch
                                size="small"
                                checked={gridParams.return_to_start}
                                onChange={(e) =>
                                  setGridParams((p) => ({
                                    ...p,
                                    return_to_start: e.target.checked,
                                  }))
                                }
                              />
                            }
                            label={<Typography variant="body2">Return to start key point</Typography>}
                          />
                        </>
                      )}
                      {gridParams.task_type === "grid_surveillance" && (
                        <>
                          <TextField
                            variant="filled"
                            label={
                              <InfoLabel
                                label="Grid spacing (m)"
                                info="Typical spacing is 30-50m for wide surveillance coverage."
                              />
                            }
                            InputLabelProps={INFO_INPUT_LABEL_PROPS}
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.grid_spacing_m}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                grid_spacing_m: Math.min(300, Math.max(2, value)),
                              }));
                            }}
                            inputProps={{ min: 2, max: 300, step: 1 }}
                          />
                          <TextField
                            variant="filled"
                            label={
                              <InfoLabel
                                label="Grid angle (°)"
                                info="Adjust heading of grid lanes to align with site shape."
                              />
                            }
                            InputLabelProps={INFO_INPUT_LABEL_PROPS}
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.grid_angle_deg}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                grid_angle_deg: Math.min(179, Math.max(0, value)),
                              }));
                            }}
                            inputProps={{ min: 0, max: 179, step: 1 }}
                          />
                          <TextField
                            variant="filled"
                            label="Safety inset (m)"
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.safety_inset_m}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                safety_inset_m: Math.min(100, Math.max(0, value)),
                              }));
                            }}
                            inputProps={{ min: 0, max: 100, step: 0.5 }}
                          />
                        </>
                      )}
                      {gridParams.task_type === "event_triggered_patrol" && (
                        <>
                          <TextField
                            variant="filled"
                            select
                            label="Trigger type"
                            size="small"
                            fullWidth
                            value={gridParams.trigger_type}
                            onChange={(e) =>
                              setGridParams((p) => ({
                                ...p,
                                trigger_type: e.target.value as PatrolTriggerType,
                              }))
                            }
                          >
                            <MenuItem value="motion_sensor">Motion sensor</MenuItem>
                            <MenuItem value="fence_alarm">Fence alarm</MenuItem>
                            <MenuItem value="camera_detection">Camera detection</MenuItem>
                            <MenuItem value="night_schedule">Night schedule</MenuItem>
                            <MenuItem value="unknown_vehicle">Unknown vehicle</MenuItem>
                          </TextField>
                          <TextField
                            variant="filled"
                            label="Verification loiter (s)"
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.verification_loiter_s}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                verification_loiter_s: Math.min(600, Math.max(0, value)),
                              }));
                            }}
                            inputProps={{ min: 0, max: 600, step: 1 }}
                          />
                          <TextField
                            variant="filled"
                            label="Verification radius (m)"
                            type="number"
                            size="small"
                            fullWidth
                            value={gridParams.verification_radius_m}
                            onChange={(e) => {
                              const value = Number(e.target.value);
                              if (!Number.isFinite(value)) return;
                              setGridParams((p) => ({
                                ...p,
                                verification_radius_m: Math.min(150, Math.max(0, value)),
                              }));
                            }}
                            inputProps={{ min: 0, max: 150, step: 1 }}
                          />
                          <TextField
                            variant="filled"
                            label="Target label (optional)"
                            size="small"
                            fullWidth
                            value={gridParams.target_label}
                            onChange={(e) =>
                              setGridParams((p) => ({
                                ...p,
                                target_label: e.target.value,
                              }))
                            }
                            placeholder="e.g. unknown vehicle"
                          />
                          <FormControlLabel
                            control={
                              <Switch
                                size="small"
                                checked={gridParams.track_target}
                                onChange={(e) =>
                                  setGridParams((p) => ({
                                    ...p,
                                    track_target: e.target.checked,
                                  }))
                                }
                              />
                            }
                            label={<Typography variant="body2">Track target</Typography>}
                          />
                          <FormControlLabel
                            control={
                              <Switch
                                size="small"
                                checked={gridParams.auto_stream_video}
                                onChange={(e) =>
                                  setGridParams((p) => ({
                                    ...p,
                                    auto_stream_video: e.target.checked,
                                  }))
                                }
                              />
                            }
                            label={<Typography variant="body2">Stream video to operator</Typography>}
                          />
                        </>
                      )}
                      <Box sx={{ gridColumn: "1 / -1" }}>
                        <Typography variant="caption" sx={{ color: "text.secondary" }}>
                          AI Tasks During Flight
                        </Typography>
                        <Stack
                          direction={{ xs: "column", md: "row" }}
                          spacing={1}
                          sx={{ mt: 0.5, flexWrap: "wrap", rowGap: 1 }}
                        >
                          {[
                            ["intruder_detection", "Intruder detection"],
                            ["vehicle_detection", "Vehicle detection"],
                            ["fence_breach_detection", "Fence breach detection"],
                            ["motion_detection", "Motion detection"],
                          ].map(([taskId, label]) => {
                            const task = taskId as GridParams["ai_tasks"][number];
                            const checked = gridParams.ai_tasks.includes(task);
                            return (
                              <FormControlLabel
                                key={task}
                                control={
                                  <Switch
                                    size="small"
                                    checked={checked}
                                    onChange={(e) => {
                                      setGridParams((p) => {
                                        if (e.target.checked) {
                                          if (p.ai_tasks.includes(task)) return p;
                                          return { ...p, ai_tasks: [...p.ai_tasks, task] };
                                        }
                                        const next = p.ai_tasks.filter((t) => t !== task);
                                        return {
                                          ...p,
                                          ai_tasks: next.length > 0 ? next : p.ai_tasks,
                                        };
                                      });
                                    }}
                                  />
                                }
                                label={<Typography variant="caption">{label}</Typography>}
                              />
                            );
                          })}
                        </Stack>
                      </Box>
                      {isGridSurveillance && (alt < 20 || alt > 35) && (
                        <Alert severity="info" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
                          Grid surveillance typically runs at 20-35m altitude for stable wide-area monitoring.
                        </Alert>
                      )}
                      {!hasRequiredTaskGeometry && (
                        <Alert severity="info" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
                          {isWaypointPatrol
                            ? "Add key points on the map (Gate, Parking, Storage, etc.) to generate a waypoint patrol preview."
                            : isEventTriggeredPatrol
                              ? "Set an event location point on the map. For night schedule trigger, a property polygon can be used as fallback."
                            : "Draw or select a property polygon above to generate a patrol preview."}
                        </Alert>
                      )}
                      {isEventTriggeredPatrol && eventLocation && (
                        <Chip
                          size="small"
                          color="error"
                          variant="outlined"
                          sx={{ gridColumn: "1 / -1", width: "fit-content" }}
                          label={`Event at ${eventLocation.lat.toFixed(5)}, ${eventLocation.lon.toFixed(5)}`}
                        />
                      )}
                      {hasRequiredTaskGeometry && gridPreview && (
                        <Stack
                          direction="row"
                          spacing={1}
                          sx={{ flexWrap: "wrap", rowGap: 1, gridColumn: "1 / -1" }}
                        >
                          <Chip
                            size="small"
                            color="success"
                            label={`${gridPreview.length} patrol waypoints`}
                          />
                          {typeof gridPreviewStats?.total_route_m === "number" && (
                            <Chip
                              size="small"
                              color="primary"
                              variant="outlined"
                              label={`Route ${gridPreviewStats.total_route_m.toFixed(1)} m`}
                            />
                          )}
                          {typeof gridPreviewStats?.patrol_loops === "number" && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`${gridPreviewStats.patrol_loops} loop(s)`}
                            />
                          )}
                          {typeof gridPreviewStats?.key_points === "number" && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`${gridPreviewStats.key_points} checkpoints`}
                            />
                          )}
                          {typeof gridPreviewStats?.rows === "number" && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`${gridPreviewStats.rows} grid rows`}
                            />
                          )}
                          {typeof gridPreviewStats?.grid_spacing_m === "number" && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`Spacing ${gridPreviewStats.grid_spacing_m.toFixed(1)} m`}
                            />
                          )}
                          {gridPreviewStats?.trigger_type && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`Trigger ${gridPreviewStats.trigger_type}`}
                            />
                          )}
                          {gridPreviewStats?.trigger_action && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`Action ${gridPreviewStats.trigger_action}`}
                            />
                          )}
                          {typeof gridPreviewStats?.path_offset_applied_m === "number" && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`Offset ${gridPreviewStats.path_offset_applied_m.toFixed(
                                1
                              )} m`}
                            />
                          )}
                          {typeof gridPreviewStats?.estimated_duration_s === "number" && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`ETA ${(gridPreviewStats.estimated_duration_s / 60).toFixed(
                                1
                              )} min`}
                            />
                          )}
                        </Stack>
                      )}
                      {gridPreviewTooDense && !isWaypointPatrol && (
                        <Alert severity="warning" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
                          Patrol preview is too dense ({gridPreview?.length}/
                          {MAX_GRID_PREVIEW_WAYPOINTS} waypoints). Increase segment
                          length or reduce patrol loops before launch.
                        </Alert>
                      )}
                      {gridPreviewError && (
                        <Alert severity="warning" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
                          {gridPreviewError}
                        </Alert>
                      )}
                      {previewLoading && (
                        <Box
                          sx={{
                            display: "flex",
                            justifyContent: "center",
                            gridColumn: "1 / -1",
                          }}
                        >
                          <CircularProgress size={20} />
                        </Box>
                      )}
                    </Box>
                  </Paper>
                </Box>

                <Typography variant="body2" sx={{ mt: 1 }}>
                  {isWaypointPatrol
                    ? "Add sensitive checkpoints (Gate, Parking, Warehouse doors, Roof), tune waypoint actions, and preview the verification route before launch."
                    : isGridSurveillance
                      ? "Draw a property polygon, configure coverage spacing, and preview the full-area surveillance grid before launch."
                      : isEventTriggeredPatrol
                        ? "Select a trigger profile, set an event location, and preview rapid verification flow (takeoff, goto, verify/track, stream)."
                      : "Draw a property polygon, tune perimeter parameters, and preview the generated patrol route before launch."}
                </Typography>

                <MissionVideoPanel
                  title="Patrol Camera"
                  imgAlt="Private patrol camera stream"
                  disconnectedMessage="Connect the drone to view the patrol stream."
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

              <Box sx={{ width: { xs: "100%", md: 300 } }}>
                <Stack spacing={2}>
                  <MissionPreflightPanel
                    apiBase={API_BASE_CLEAN}
                    missionType="perimeter_patrol"
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
                  <TextField variant="filled"
                    label="Mission name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    size="small"
                    fullWidth
                    required
                    error={!name.trim()}
                    helperText={!name.trim() ? "Mission name is required" : " "}
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
                    error={
                      altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)
                    }
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
                      previewLoading ||
                      (gridPreviewTooDense && !isWaypointPatrol) ||
                      !!gridPreviewError ||
                      !name.trim() ||
                      altInput === "" ||
                      Number(altInput) < 1 ||
                      Number(altInput) > 500 ||
                      !hasRequiredTaskGeometry
                    }
                    fullWidth
                    sx={{ mt: 1 }}
                    color="success"
                  >
                    {sending ? (
                      <>
                        <CircularProgress size={20} sx={{ mr: 1 }} />
                        {isWaypointPatrol
                          ? "Starting Waypoint Patrol..."
                          : isGridSurveillance
                            ? "Starting Grid Surveillance..."
                            : isEventTriggeredPatrol
                              ? "Starting Event-Triggered Patrol..."
                            : "Starting Perimeter Patrol..."}
                      </>
                    ) : (
                      isWaypointPatrol
                        ? "Start Waypoint Patrol"
                        : isGridSurveillance
                          ? "Start Grid Surveillance"
                          : isEventTriggeredPatrol
                            ? "Start Event-Triggered Patrol"
                          : "Start Perimeter Patrol"
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

            {isWaypointPatrol && waypoints.length > 0 && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" sx={{ mb: 1 }}>
                  Key Points
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

            {isEventTriggeredPatrol && eventLocation && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" sx={{ mb: 1 }}>
                  Trigger Event
                </Typography>
                <Typography variant="body2">
                  Location: {eventLocation.lat.toFixed(6)}, {eventLocation.lon.toFixed(6)}
                </Typography>
                <Typography variant="body2">
                  Trigger: {gridParams.trigger_type} | Track: {gridParams.track_target ? "yes" : "no"} | Stream: {gridParams.auto_stream_video ? "yes" : "no"}
                </Typography>
              </Box>
            )}

            {missionStatus && (activeFlightId || waypoints.length > 0 || !!eventLocation) && (
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
      <Dialog open={Boolean(pendingDeleteField)} onClose={closeDeleteFieldDialog}>
        <DialogTitle>Delete Field</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Delete field "{pendingDeleteField?.name}"? This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDeleteFieldDialog} disabled={deletingField}>
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={confirmDeleteSelectedField}
            disabled={deletingField}
          >
            {deletingField ? "Deleting..." : "Delete"}
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        open={uiNotice.open}
        autoHideDuration={4000}
        onClose={handleUiNoticeClose}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <Alert onClose={handleUiNoticeClose} severity={uiNotice.severity} sx={{ width: "100%" }}>
          {uiNotice.message}
        </Alert>
      </Snackbar>
    </>
  );
}
