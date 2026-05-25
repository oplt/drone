import { useEffect, useRef, useState, useCallback, useMemo, useContext } from "react";
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
  MenuItem,
  IconButton,
  Tooltip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from "@mui/material";
import Header from "../../../components/dashboard/Header";
import InfoLabel from "../../../components/dashboard/InfoLabel";
import type { TerraDraw } from "terra-draw";
import { GroundOverlay, Polyline, Polygon, OverlayView } from "@react-google-maps/api";
import { getToken } from "../../../auth";
import DroneSvg from "../../../assets/Drone.svg?react";
import SvgIcon from "@mui/material/SvgIcon";
import RoomIcon from "@mui/icons-material/Room";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import { GoogleMapsContext } from "../../../utils/googleMaps";
import PentagonOutlinedIcon from "@mui/icons-material/PentagonOutlined";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import CropSquareOutlinedIcon from "@mui/icons-material/CropSquareOutlined";
import RadioButtonUncheckedOutlinedIcon from "@mui/icons-material/RadioButtonUncheckedOutlined";
import PanToolAltOutlinedIcon from "@mui/icons-material/PanToolAltOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import { CesiumViewControls } from "../../../components/dashboard/tasks/CesiumViewControls";
import { ErrorAlerts } from "../../../components/dashboard/tasks/ErrorAlerts";
import { MissionCommandPanel } from "../../../components/dashboard/tasks/MissionCommandPanel";
import { MissionPreflightPanel } from "../../../components/dashboard/tasks/MissionPreflightPanel";
import { TaskControlFrame } from "../../../components/dashboard/tasks/TaskControlFrame";
import { MissionMapViewport } from "../../../components/dashboard/tasks/MissionMapViewport";
import type { MissionMapEngine } from "../../../components/dashboard/tasks/MissionMapViewport";
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
  getIrrigationMissionSummary,
  startMissionWithPreflight,
  triggerIrrigationMissionProcessing,
  type IrrigationMissionSummary,
  type PreflightRunResponse,
} from "../../../utils/api";

type Waypoint = { lat: number; lon: number; alt: number };
type CesiumViewMode = "top" | "tilted" | "follow" | "fpv" | "orbit";
type DrawMode = "none" | "point" | "polyline" | "polygon" | "rectangle" | "circle";
type TerraFeature = TerraDrawFeature;
type LonLat = [number, number];
type GridParams = {
  row_spacing_m: number;
  grid_angle_deg: number | null;
  slope_aware: boolean;
  safety_inset_m: number;
  terrain_follow: boolean;
  agl_m: number;
  pattern_mode: "boustrophedon" | "crosshatch";
  crosshatch_angle_offset_deg: number;
  start_corner: "auto" | "nw" | "ne" | "sw" | "se";
  lane_strategy: "serpentine" | "one_way";
  row_stride: number;
  row_phase_m: number;
};
type GridPreviewWaypoint = { lat: number; lon: number };
type GridPreviewStats = {
  rows?: number;
  waypoints?: number;
  route_m?: number;
  area_m2?: number;
  passes?: number;
  start_corner?: string;
  lane_strategy?: string;
  row_stride?: number;
  row_phase_m?: number;
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
type IrrigationZoneStyle = {
  fillColor: string;
  strokeColor: string;
  label: string;
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

const MAX_GRID_PREVIEW_WAYPOINTS = 2200;
const GRID_PREVIEW_DEBOUNCE_MS = 250;
const CESIUM_MAX_SAFE_ZOOM = 16;
const INFO_INPUT_LABEL_PROPS = {
  shrink: true,
  sx: { pointerEvents: "auto" },
} as const;

export default function FieldPage() {
  const [controlFrameExpanded, setControlFrameExpanded] = useState(true);
  const [fieldName, setFieldName] = useState("Field A");
  const [fieldBorder, setFieldBorder] = useState<LonLat[] | null>(null);
  const [fields, setFields] = useState<FieldFeature[]>([]);
  const [loadingFields, setLoadingFields] = useState(false);
  const [selectedFieldId, setSelectedFieldId] = useState<number | null>(null);
  const [fieldsRefreshNonce, setFieldsRefreshNonce] = useState(0);
  const [savingField, setSavingField] = useState(false);
  const [deletingField, setDeletingField] = useState(false);
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

  const polygonPathToLonLat = (poly: google.maps.Polygon): LonLat[] => {
    const path = poly.getPath();
    const pts: LonLat[] = [];
    for (let i = 0; i < path.getLength(); i++) {
      const p = path.getAt(i);
      pts.push([p.lng(), p.lat()]);
    }
    return pts;
  };

  const wirePolygonEditListeners = (poly: google.maps.Polygon) => {
    const path = poly.getPath();

    const update = () => setFieldBorder(polygonPathToLonLat(poly));

    update();

    path.addListener("set_at", update);
    path.addListener("insert_at", update);
    path.addListener("remove_at", update);
  };

  const clearFieldBorder = () => {
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
  };

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
      alert(`Saved field "${data.name}" (id=${data.id})`);
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
      alert(`Updated field "${data.name}" (id=${data.id})`);
      setFieldsRefreshNonce((n) => n + 1);
    } catch (e: any) {
      addError(e?.message ?? "Failed to update field");
    } finally {
      setSavingField(false);
    }
  };

  const mapRef = useRef<google.maps.Map | null>(null);
  const fieldPolygonRef = useRef<google.maps.Polygon | null>(null);
  const missionLaunchInFlightRef = useRef(false);
  const gridPreviewAbortRef = useRef<AbortController | null>(null);
  const [userCenter, setUserCenter] = useState<LatLng | null>(null);
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const [alt, setAlt] = useState(30);
  const [altInput, setAltInput] = useState("30");
  const [name, setName] = useState("field-plan-1");
  const [sending, setSending] = useState(false);
  const [preflightRun, setPreflightRun] =
    useState<PreflightRunResponse | null>(null);
  const [gridParams, setGridParams] = useState<GridParams>({
    row_spacing_m: 7.5,
    grid_angle_deg: null,
    slope_aware: false,
    safety_inset_m: 1.5,
    terrain_follow: false,
    agl_m: 30,
    pattern_mode: "boustrophedon",
    crosshatch_angle_offset_deg: 90,
    start_corner: "auto",
    lane_strategy: "serpentine",
    row_stride: 1,
    row_phase_m: 0,
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
  const [previewLoading, setPreviewLoading] = useState(false);
  const [center, setCenter] = useState(defaultCenter);
  const [loadingLocation, setLoadingLocation] = useState(true);
  const { errors, addError, clearErrors, dismissError } = useErrors();
  const [exclusionZones, setExclusionZones] = useState<LonLat[][]>([]);
  const [fieldTilesetUrl, setFieldTilesetUrl] = useState<string | null>(null);
  const [mapZoom, setMapZoom] = useState(12);
  const [lastMissionId, setLastMissionId] = useState<string | null>(null);
  const [irrigationSummary, setIrrigationSummary] = useState<IrrigationMissionSummary | null>(null);
  const [irrigationLoading, setIrrigationLoading] = useState(false);
  const [irrigationRefreshing, setIrrigationRefreshing] = useState(false);
  const [irrigationError, setIrrigationError] = useState<string | null>(null);
  const [streamKey, setStreamKey] = useState(Date.now());
  const [mapReady, setMapReady] = useState(false);
  const videoToken = getToken();
  const waypointMarkersRef = useRef<any[]>([]);
  const [useCesium, setUseCesium] = useState(false);
  const [mapEngine, setMapEngine] = useState<MissionMapEngine>("google");
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
  const trackedMissionId = activeFlightId ?? lastMissionId;
  const droneCenter = useDroneCenter(telemetry);
  const { heading, armed } = useMissionCommandMetrics(telemetry);

  const handleCesiumPick = useCallback(
    (p: { lat: number; lng: number }) => {
      setWaypoints((prev) => [...prev, { lat: p.lat, lon: p.lng, alt }]);
    },
    [alt]
  );

  const handleMapEngineChange = useCallback((next: MissionMapEngine) => {
    setMapEngine(next);
    setUseCesium(next === "cesium");
  }, []);

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

  useEffect(() => {
    if (!trackedMissionId) {
      setIrrigationSummary(null);
      setIrrigationError(null);
      return;
    }

    const token = getToken();
    if (!token) return;
    let cancelled = false;

    const loadSummary = async (background: boolean) => {
      if (!background) setIrrigationLoading(true);
      setIrrigationRefreshing(background);
      try {
        const summary = await getIrrigationMissionSummary(
          trackedMissionId,
          token,
          API_BASE_CLEAN
        );
        if (!cancelled) {
          setIrrigationSummary(summary);
          setIrrigationError(null);
        }
      } catch (error: unknown) {
        if (!cancelled) {
          setIrrigationError(
            error instanceof Error ? error.message : "Failed to load irrigation outputs"
          );
        }
      } finally {
        if (!cancelled) {
          setIrrigationLoading(false);
          setIrrigationRefreshing(false);
        }
      }
    };

    void loadSummary(false);
    const timer = window.setInterval(() => {
      void loadSummary(true);
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [API_BASE_CLEAN, trackedMissionId]);

const onMapLoad = useCallback((map: google.maps.Map) => {
  mapRef.current = map;
  setMapReady(true);
}, []);


  const onMapUnmount = useCallback(() => {
    if (fieldPolygonRef.current) {
      fieldPolygonRef.current.setMap(null);
      fieldPolygonRef.current = null;
    }
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
  const irrigationLayer = irrigationSummary?.layer ?? null;
  const irrigationZoneStyles = useMemo<Record<string, IrrigationZoneStyle>>(
    () => ({
      under_irrigated: {
        fillColor: "#d97706",
        strokeColor: "#92400e",
        label: "Dry zone",
      },
      overwatered: {
        fillColor: "#0284c7",
        strokeColor: "#075985",
        label: "Overwatered",
      },
      uneven_distribution: {
        fillColor: "#7c3aed",
        strokeColor: "#5b21b6",
        label: "Uneven band",
      },
    }),
    []
  );
  const irrigationZonePaths = useMemo(
    () =>
      (irrigationSummary?.anomaly_zones ?? [])
        .map((zone) => {
          const coords = zone?.polygon_geojson?.coordinates?.[0];
          if (!Array.isArray(coords) || coords.length < 4) return null;
          return {
            zone,
            path: coords.map((pair) => ({
              lng: Number(pair[0]),
              lat: Number(pair[1]),
            })),
          };
        })
        .filter(Boolean) as Array<{
        zone: IrrigationMissionSummary["anomaly_zones"][number];
        path: LatLng[];
      }>,
    [irrigationSummary]
  );
  const irrigationCapturePreview = irrigationSummary?.captures?.slice(0, 3) ?? [];
  const overlayBounds = irrigationLayer?.tile_manifest?.bounds ?? null;

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
    [stripClosedRing]
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
  }, [addError, lonLatRingToPath, stripClosedRing]);

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
          if (rawUrl) {
            setFieldTilesetUrl(toAbsoluteAssetUrl(rawUrl));
            handleMapEngineChange("cesium");
            setCesiumViewMode("top");
          } else {
            setFieldTilesetUrl(null);
          }
        }
      } catch {
        if (!cancelled) setFieldTilesetUrl(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [API_BASE_CLEAN, handleMapEngineChange, selectedFieldId, toAbsoluteAssetUrl]);

  const selectField = useCallback(
    (f: FieldFeature) => {
      handleMapEngineChange("google");
      setSelectedFieldId(f.id);
      setFieldName(f.name);
      setFieldBorder(f.ring);
      loadRingIntoEditor(f.ring);
      focusRingOnMap(f.ring);
    },
    [focusRingOnMap, handleMapEngineChange, loadRingIntoEditor]
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
    if (selectedFieldId == null) {
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
      setFieldsRefreshNonce((n) => n + 1);
      clearFieldBorder();
      setFieldName("Field A");
      setPendingDeleteField(null);
    } catch (e: any) {
      addError(e?.message ?? "Failed to delete field");
    } finally {
      setDeletingField(false);
    }
  }, [API_BASE_CLEAN, addError, clearFieldBorder, pendingDeleteField]);

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

  const previewLegStats = useMemo(() => {
    if (!gridPreview || !gridPreviewMask) return null;
    const workLegs = gridPreviewMask.filter(Boolean).length;
    const transitLegs = gridPreviewMask.length - workLegs;
    return { workLegs, transitLegs };
  }, [gridPreview, gridPreviewMask]);
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
    if (waypoints.length === 0) return;

    waypoints.forEach((p) => {
      const content = document.createElement("div");
      content.style.width = "12px";
      content.style.height = "12px";
      content.style.borderRadius = "50%";
      content.style.background = "#1976d2";
      content.style.border = "2px solid #ffffff";
      content.style.boxShadow = "0 2px 6px rgba(0,0,0,0.2)";

      const marker = new markerLib.AdvancedMarkerElement({
        map: mapRef.current,
        position: { lat: p.lat, lng: p.lon },
        content,
        title: "Waypoint",
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
  }, [isLoaded, mapReady, terraDrawMode, waypoints]);

useEffect(() => {
  if (mapEngine !== "google") return;

  const modeMap: Record<DrawMode, TerraDrawEditorMode> = {
    polygon: "polygon",
    polyline: "linestring",
    point: "point",
    rectangle: "rectangle",
    circle: "circle",
    none: "static",
  };

  const tdMode = modeMap[drawMode];
  if (tdMode) setTerraDrawMode(tdMode);
}, [drawMode, mapEngine]);

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
      setWaypoints((prev) => [...prev, { lat, lon: lng, alt }]);
    },
    [alt, terraDrawMode]
  );
  const handleDrawingToolSelection = useCallback(
    (toolMode: TerraDrawToolMode) => {
      if (mapEngine !== "google") {
        const cesiumModeMap: Record<TerraDrawToolMode, DrawMode> = {
          polygon: "polygon",
          linestring: "polyline",
          point: "point",
          rectangle: "rectangle",
          circle: "circle",
          freehand: "polygon",
          select: "none",
        };
        setDrawMode(cesiumModeMap[toolMode] ?? "none");
        return;
      }

      setTerraDrawMode(toolMode);
    },
    [mapEngine]
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
        setWaypoints(
          result.coordinates.map(([lon, lat]) => ({
            lat,
            lon,
            alt,
          }))
        );
      } else if (result.type === "point") {
        const [lon, lat] = result.coordinates;
        setWaypoints((prev) => [...prev, { lat, lon, alt }]);
      }

      setDrawMode("none");
    },
    [alt, stripClosedRing]
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
      if (mapEngine === "google" && terraDrawMode !== "static" && terraDrawMode !== "select") {
        setPreviewLoading(false);
        return;
      }
      if (!fieldBorder || fieldBorder.length < 3) {
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
        const res = await fetch(`${API_BASE_CLEAN}/tasks/missions/grid-preview`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          signal,
          body: JSON.stringify({
            field_polygon_lonlat: fieldBorder,
            row_spacing_m: gridParams.row_spacing_m,
            grid_angle_deg: gridParams.grid_angle_deg,
            safety_inset_m: gridParams.safety_inset_m,
            pattern_mode: gridParams.pattern_mode,
            crosshatch_angle_offset_deg: gridParams.crosshatch_angle_offset_deg,
            start_corner: gridParams.start_corner,
            lane_strategy: gridParams.lane_strategy,
            row_stride: gridParams.row_stride,
            row_phase_m: gridParams.row_phase_m,
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
          setGridPreviewError(detail || `Grid preview failed (HTTP ${res.status})`);
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
        setGridPreviewError("Grid preview failed. Please try again.");
      } finally {
        if (!signal.aborted) setPreviewLoading(false);
      }
    },
    [API_BASE_CLEAN, fieldBorder, gridParams, terraDrawMode, useCesium]
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

    if (!fieldBorder || fieldBorder.length < 3) {
      addError("Draw or select a field polygon before starting a grid survey");
      return;
    }
    if (gridPreview && gridPreview.length > MAX_GRID_PREVIEW_WAYPOINTS) {
      addError(
        `Grid preview is too dense for safe execution (${gridPreview.length}/${MAX_GRID_PREVIEW_WAYPOINTS} waypoints). Increase row spacing, increase row stride, or split the field.`
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
        mission_type: "grid",
        grid: {
          field_polygon_lonlat: fieldBorder,
          row_spacing_m: gridParams.row_spacing_m,
          grid_angle_deg: gridParams.grid_angle_deg,
          slope_aware: gridParams.slope_aware,
          safety_inset_m: gridParams.safety_inset_m,
          terrain_follow: gridParams.terrain_follow,
          agl_m: gridParams.agl_m,
          pattern_mode: gridParams.pattern_mode,
          crosshatch_angle_offset_deg: gridParams.crosshatch_angle_offset_deg,
          start_corner: gridParams.start_corner,
          lane_strategy: gridParams.lane_strategy,
          row_stride: gridParams.row_stride,
          row_phase_m: gridParams.row_phase_m,
        },
      };

      const { preflight, mission: data } = await startMissionWithPreflight(
        payload,
        token,
        API_BASE_CLEAN,
      );
      setPreflightRun(preflight);
      alert(`Grid Survey: "${data.mission_name}" started! Tracking flight...`);

      setPendingFlightId(data.flight_id ?? null);
      setLastMissionId(data.flight_id ?? null);
      setIrrigationSummary(null);
      setIrrigationError(null);

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
  const cesiumFieldBoundary = useMemo(
    () => (fieldBorder && fieldBorder.length >= 3 ? fieldBorder : null),
    [fieldBorder]
  );
  const cesiumPlannedRoute = useMemo(() => {
    if (gridPreview && gridPreview.length >= 2) {
      return gridPreview.map((p) => [p.lon, p.lat] as LonLat);
    }
    if (waypoints.length >= 2) {
      return waypoints.map((p) => [p.lon, p.lat] as LonLat);
    }
    return null;
  }, [gridPreview, waypoints]);

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
            <Typography variant="h5">Field Operations</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Configure field routes, stream telemetry, and monitor imagery in
              real time.
            </Typography>
          </div>
          <MissionStatusChips droneConnected={droneConnected} wsConnected={wsConnected} />
        </Stack>

        <ErrorAlerts
          errors={errors}
          onDismiss={dismissError}
          onClearAll={clearErrors}
        />

        {mapEngine === "google" && !apiKey ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Missing Google Maps API Key. Please set
            VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY in your .env file.
          </Alert>
        ) : mapEngine === "google" && loadError ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load Google Maps. {loadError.message} Ensure the Maps
            JavaScript API is enabled, billing is active, and the key allows
            your domain.
          </Alert>
        ) : mapEngine === "google" && !mapId ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Google Maps Map ID is not set. Advanced markers require a Map ID.
            Set VITE_GOOGLE_MAPS_MAP_ID to remove this warning.
          </Alert>
        ) : (
          <>
            <TerraDrawController
              map={mapReady ? mapRef.current : null}
              enabled={mapEngine === "google"}
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
                <Box
                  sx={{
                    borderRadius: 2,
                    overflow: "hidden",
                    border: "1px solid",
                    borderColor: "divider",
                    backgroundColor: "background.paper",
                  }}
                >
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
                    leafletMapProps={{
                      center: mapCenter,
                      zoom: mapZoom,
                      waypoints,
                      fieldBoundary: cesiumFieldBoundary,
                      plannedRoute: cesiumPlannedRoute,
                      exclusionZones,
                      droneCenter,
                      userCenter,
                      onPickLatLng: handleCesiumPick,
                      drawMode,
                      onDrawComplete: handleCesiumDrawComplete,
                      height: 400,
                    }}
                    mapLibreMapProps={{
                      center: mapCenter,
                      zoom: mapZoom,
                      waypoints,
                      fieldBoundary: cesiumFieldBoundary,
                      plannedRoute: cesiumPlannedRoute,
                      exclusionZones,
                      droneCenter,
                      userCenter,
                      onPickLatLng: handleCesiumPick,
                      drawMode,
                      onDrawComplete: handleCesiumDrawComplete,
                      height: 400,
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

                        {gridPreview && gridPreview.length >= 2 && (
                          <>
                            {gridPreview.slice(0, -1).map((wp, i) =>
                              gridPreviewMask?.[i] ? (
                                <Polyline
                                  key={`work-${i}`}
                                  path={[
                                    { lat: wp.lat, lng: wp.lon },
                                    {
                                      lat: gridPreview[i + 1].lat,
                                      lng: gridPreview[i + 1].lon,
                                    },
                                  ]}
                                  options={{
                                    strokeColor: "#2e7d32",
                                    strokeOpacity: 0.85,
                                    strokeWeight: 2,
                                  }}
                                />
                              ) : (
                                <Polyline
                                  key={`turn-${i}`}
                                  path={[
                                    { lat: wp.lat, lng: wp.lon },
                                    {
                                      lat: gridPreview[i + 1].lat,
                                      lng: gridPreview[i + 1].lon,
                                    },
                                  ]}
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
                              )
                            )}
                          </>
                        )}

                        {overlayBounds?.north != null &&
                          overlayBounds?.south != null &&
                          overlayBounds?.east != null &&
                          overlayBounds?.west != null &&
                          irrigationLayer?.tile_manifest?.image_uri && (
                            <GroundOverlay
                              url={toAbsoluteAssetUrl(irrigationLayer.tile_manifest.image_uri)}
                              bounds={{
                                north: overlayBounds.north,
                                south: overlayBounds.south,
                                east: overlayBounds.east,
                                west: overlayBounds.west,
                              }}
                              opacity={0.55}
                            />
                          )}

                        {irrigationZonePaths.map(({ zone, path }) => {
                          const style =
                            irrigationZoneStyles[zone.type] ??
                            ({
                              fillColor: "#ef4444",
                              strokeColor: "#991b1b",
                              label: zone.type,
                            } satisfies IrrigationZoneStyle);
                          return (
                            <Polygon
                              key={`irrigation-zone-${zone.id}`}
                              paths={path}
                              options={{
                                clickable: true,
                                fillColor: style.fillColor,
                                fillOpacity: 0.28,
                                strokeColor: style.strokeColor,
                                strokeOpacity: 0.95,
                                strokeWeight: 2,
                                zIndex: 24,
                              }}
                            />
                          );
                        })}

                        {(irrigationSummary?.inspection_points ?? []).map((point) => (
                          <OverlayView
                            key={`inspection-${point.id}`}
                            position={{ lat: point.lat, lng: point.lon }}
                            mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}
                          >
                            <div
                              style={{
                                transform: "translate(-50%, -50%)",
                                display: "flex",
                                flexDirection: "column",
                                alignItems: "center",
                                gap: 2,
                              }}
                            >
                              <div
                                style={{
                                  width: 18,
                                  height: 18,
                                  borderRadius: "999px",
                                  background: "#111827",
                                  color: "#ffffff",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  fontSize: 10,
                                  fontWeight: 700,
                                  boxShadow: "0 4px 10px rgba(15,23,42,0.28)",
                                }}
                              >
                                {Math.max(1, Math.round(point.priority * 9))}
                              </div>
                              <div
                                style={{
                                  background: "rgba(255,255,255,0.96)",
                                  borderRadius: 4,
                                  padding: "2px 6px",
                                  fontSize: 10,
                                  whiteSpace: "nowrap",
                                  boxShadow: "0 2px 8px rgba(15,23,42,0.2)",
                                }}
                              >
                                {point.label}
                              </div>
                            </div>
                          </OverlayView>
                        ))}

                        {terraDrawMode === "static" && waypoints.length >= 2 && (
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
                          bgcolor: "background.paper",
                        }}
                      >
                        <Stack direction="column" spacing={0.5}>
                          {[
                            {
                              mode: "polygon",
                              label: "Polygon",
                              icon: <PentagonOutlinedIcon fontSize="small" />,
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
                              mode: "select",
                              label: "Select",
                              icon: <PanToolAltOutlinedIcon fontSize="small" />,
                            },
                          ].map((tool) => {
                            const selected = mapEngine !== "google"
                              ? (drawMode === "point" && tool.mode === "point") ||
                                (drawMode === "polyline" && tool.mode === "linestring") ||
                                (drawMode === "polygon" &&
                                  ["polygon", "rectangle", "circle"].includes(
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
                                  if (mapEngine !== "google") {
                                    if (drawMode !== "none") {
                                      setDrawMode("none");
                                      return;
                                    }
                                    if (fieldBorder && fieldBorder.length > 0) {
                                      setFieldBorder((prev) => {
                                        if (!prev || prev.length <= 1) return null;
                                        return prev.slice(0, -1) as LonLat[];
                                      });
                                      return;
                                    }
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
                                  mapEngine !== "google"
                                    ? drawMode === "none" &&
                                      (!fieldBorder || fieldBorder.length === 0) &&
                                      waypoints.length === 0
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
                                      onUseCesiumChange={(next) =>
                                        handleMapEngineChange(next ? "cesium" : "google")
                                      }
                                      mapEngine={mapEngine}
                                      onMapEngineChange={handleMapEngineChange}
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
                    Grid Survey Parameters
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
                      <TextField variant="filled"
                        select
                        label={
                          <InfoLabel
                            label="Pattern mode"
                            info="Boustrophedon is a classic lawnmower sweep. Crosshatch adds a second pass."
                          />
                        }
                        InputLabelProps={INFO_INPUT_LABEL_PROPS}
                        size="small"
                        fullWidth
                        value={gridParams.pattern_mode}
                        onChange={(e) =>
                          setGridParams((p) => ({
                            ...p,
                            pattern_mode: e.target.value as GridParams["pattern_mode"],
                          }))
                        }
                      >
                        <MenuItem value="boustrophedon">Boustrophedon (single pass)</MenuItem>
                        <MenuItem value="crosshatch">Crosshatch (two passes)</MenuItem>
                      </TextField>
                      <TextField variant="filled"
                        select
                        label={
                          <InfoLabel
                            label="Lane strategy"
                            info="Serpentine is efficient (classic lawnmower). One-way keeps each lane in the same direction."
                          />
                        }
                        InputLabelProps={INFO_INPUT_LABEL_PROPS}
                        size="small"
                        fullWidth
                        value={gridParams.lane_strategy}
                        onChange={(e) =>
                          setGridParams((p) => ({
                            ...p,
                            lane_strategy: e.target.value as GridParams["lane_strategy"],
                          }))
                        }
                      >
                        <MenuItem value="serpentine">Serpentine (recommended)</MenuItem>
                        <MenuItem value="one_way">One-way lanes</MenuItem>
                      </TextField>
                      <TextField variant="filled"
                        select
                        label={
                          <InfoLabel
                            label="Start corner"
                            info="Choose where lane sequencing starts. Auto keeps the default planner behavior."
                          />
                        }
                        InputLabelProps={INFO_INPUT_LABEL_PROPS}
                        size="small"
                        fullWidth
                        value={gridParams.start_corner}
                        onChange={(e) =>
                          setGridParams((p) => ({
                            ...p,
                            start_corner: e.target.value as GridParams["start_corner"],
                          }))
                        }
                      >
                        <MenuItem value="auto">Auto</MenuItem>
                        <MenuItem value="sw">South-West</MenuItem>
                        <MenuItem value="se">South-East</MenuItem>
                        <MenuItem value="nw">North-West</MenuItem>
                        <MenuItem value="ne">North-East</MenuItem>
                      </TextField>
                      <TextField variant="filled"
                        label="Row spacing (m)"
                        type="number"
                        size="small"
                        fullWidth
                        value={gridParams.row_spacing_m}
                        onChange={(e) => {
                          const value = Number(e.target.value);
                          if (!Number.isFinite(value)) return;
                          setGridParams((p) => ({
                            ...p,
                            row_spacing_m: Math.max(1, value),
                          }));
                        }}
                        inputProps={{ min: 1, max: 200, step: 0.5 }}
                      />
                      <TextField variant="filled"
                        label={
                          <InfoLabel
                            label="Row stride (every Nth line)"
                            info="1 uses every line. 2 flies every second line (wider effective spacing)."
                          />
                        }
                        InputLabelProps={INFO_INPUT_LABEL_PROPS}
                        type="number"
                        size="small"
                        fullWidth
                        value={gridParams.row_stride}
                        onChange={(e) => {
                          const value = Number(e.target.value);
                          if (!Number.isFinite(value)) return;
                          setGridParams((p) => ({
                            ...p,
                            row_stride: Math.min(20, Math.max(1, Math.round(value))),
                          }));
                        }}
                        inputProps={{ min: 1, max: 20, step: 1 }}
                      />
                      <TextField variant="filled"
                        label={
                          <InfoLabel
                            label="Row phase offset (m)"
                            info="Shifts line placement to align passes with crop rows."
                          />
                        }
                        InputLabelProps={INFO_INPUT_LABEL_PROPS}
                        type="number"
                        size="small"
                        fullWidth
                        value={gridParams.row_phase_m}
                        onChange={(e) => {
                          const value = Number(e.target.value);
                          if (!Number.isFinite(value)) return;
                          setGridParams((p) => ({
                            ...p,
                            row_phase_m: Math.max(0, value),
                          }));
                        }}
                        inputProps={{ min: 0, max: 500, step: 0.5 }}
                      />
                      <TextField variant="filled"
                        label={
                          <InfoLabel
                            label="Grid angle (°, blank = auto)"
                            info="Leave blank to auto-align with terrain."
                          />
                        }
                        InputLabelProps={INFO_INPUT_LABEL_PROPS}
                        type="number"
                        size="small"
                        fullWidth
                        value={gridParams.grid_angle_deg ?? ""}
                        onChange={(e) =>
                          setGridParams((p) => ({
                            ...p,
                            grid_angle_deg:
                              e.target.value === "" ? null : Number(e.target.value),
                          }))
                        }
                        inputProps={{ min: 0, max: 179, step: 1 }}
                      />
                      {gridParams.pattern_mode === "crosshatch" && (
                        <TextField variant="filled"
                          label={
                            <InfoLabel
                              label="Crosshatch angle offset (°)"
                              info="90° gives an orthogonal second pass."
                            />
                          }
                          InputLabelProps={INFO_INPUT_LABEL_PROPS}
                          type="number"
                          size="small"
                          fullWidth
                          value={gridParams.crosshatch_angle_offset_deg}
                          onChange={(e) => {
                            const value = Number(e.target.value);
                            if (!Number.isFinite(value)) return;
                            setGridParams((p) => ({
                              ...p,
                              crosshatch_angle_offset_deg: Math.min(
                                179,
                                Math.max(1, value)
                              ),
                            }));
                          }}
                          inputProps={{ min: 1, max: 179, step: 1 }}
                        />
                      )}
                      <TextField variant="filled"
                        label="Safety inset (m)"
                        type="number"
                        size="small"
                        fullWidth
                        value={gridParams.safety_inset_m}
                        onChange={(e) =>
                          setGridParams((p) => ({
                            ...p,
                            safety_inset_m: Math.max(0, Number(e.target.value)),
                          }))
                        }
                        inputProps={{ min: 0, max: 20, step: 0.5 }}
                      />
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={gridParams.slope_aware}
                            onChange={(e) =>
                              setGridParams((p) => ({
                                ...p,
                                slope_aware: e.target.checked,
                              }))
                            }
                          />
                        }
                        label={<Typography variant="caption">Slope-aware angle</Typography>}
                      />
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={gridParams.terrain_follow}
                            onChange={(e) =>
                              setGridParams((p) => ({
                                ...p,
                                terrain_follow: e.target.checked,
                              }))
                            }
                          />
                        }
                        label={
                          <Typography variant="caption">
                            Terrain following (AGL)
                          </Typography>
                        }
                      />
                      {gridParams.terrain_follow && (
                        <TextField variant="filled"
                          label="AGL height (m)"
                          type="number"
                          size="small"
                          fullWidth
                          value={gridParams.agl_m}
                          onChange={(e) =>
                            setGridParams((p) => ({
                              ...p,
                              agl_m: Math.max(1, Number(e.target.value)),
                            }))
                          }
                          inputProps={{ min: 1, max: 200, step: 1 }}
                        />
                      )}
                      {!fieldBorder && (
                        <Alert severity="info" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
                          Draw or select a field polygon above to generate a
                          grid preview.
                        </Alert>
                      )}
                      {fieldBorder && gridPreview && (
                        <Stack
                          direction="row"
                          spacing={1}
                          sx={{ flexWrap: "wrap", rowGap: 1, gridColumn: "1 / -1" }}
                        >
                          <Chip
                            size="small"
                            color="success"
                            label={`${gridPreview.length} waypoints previewed`}
                          />
                          {typeof gridPreviewStats?.route_m === "number" && (
                            <Chip
                              size="small"
                              color="primary"
                              variant="outlined"
                              label={`Route ${gridPreviewStats.route_m.toFixed(1)} m`}
                            />
                          )}
                          {typeof gridPreviewStats?.rows === "number" && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`${gridPreviewStats.rows} rows`}
                            />
                          )}
                          {previewLegStats && (
                            <>
                              <Chip
                                size="small"
                                color="primary"
                                variant="outlined"
                                label={`${previewLegStats.workLegs} work legs`}
                              />
                              <Chip
                                size="small"
                                variant="outlined"
                                label={`${previewLegStats.transitLegs} transit legs`}
                              />
                            </>
                          )}
                        </Stack>
                      )}
                      {gridPreviewTooDense && (
                        <Alert severity="warning" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
                          Grid preview is too dense ({gridPreview?.length}/
                          {MAX_GRID_PREVIEW_WAYPOINTS} waypoints). Increase row
                          spacing or row stride before starting the survey.
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
                  Click on the map to add waypoints.
                </Typography>

              </Stack>

              <Box
                sx={{
                  width: { xs: "100%", md: controlFrameExpanded ? 620 : 360 },
                  transition: "width 180ms ease",
                }}
              >
                <Stack spacing={2}>
                  <TaskControlFrame
                    expanded={controlFrameExpanded}
                    onExpandedChange={setControlFrameExpanded}
                  >
                      <MissionPreflightPanel
                        apiBase={API_BASE_CLEAN}
                        missionType="grid"
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
                      gridPreviewTooDense ||
                      !!gridPreviewError ||
                      !name.trim() ||
                      altInput === "" ||
                      Number(altInput) < 1 ||
                      Number(altInput) > 500 ||
                      !fieldBorder ||
                      fieldBorder.length < 3
                    }
                    fullWidth
                    sx={{ mt: 1 }}
                    color="success"
                  >
                    {sending ? (
                      <>
                        <CircularProgress size={20} sx={{ mr: 1 }} />
                        Starting Grid Survey...
                      </>
                    ) : (
                      "Start Grid Survey"
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

            {trackedMissionId && (
              <Box sx={{ mt: 2, p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
                <Stack
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                  spacing={2}
                  sx={{ mb: 1 }}
                >
                  <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                    Irrigation Analysis
                  </Typography>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={irrigationRefreshing}
                    onClick={async () => {
                      const token = getToken();
                      if (!token || !trackedMissionId) return;
                      try {
                        setIrrigationRefreshing(true);
                        await triggerIrrigationMissionProcessing(
                          trackedMissionId,
                          token,
                          API_BASE_CLEAN
                        );
                        const refreshed = await getIrrigationMissionSummary(
                          trackedMissionId,
                          token,
                          API_BASE_CLEAN
                        );
                        setIrrigationSummary(refreshed);
                        setIrrigationError(null);
                      } catch (error: unknown) {
                        setIrrigationError(
                          error instanceof Error
                            ? error.message
                            : "Failed to run irrigation analysis"
                        );
                      } finally {
                        setIrrigationRefreshing(false);
                      }
                    }}
                  >
                    Reprocess
                  </Button>
                </Stack>

                {irrigationLoading ? (
                  <Stack direction="row" spacing={1} alignItems="center">
                    <CircularProgress size={18} />
                    <Typography variant="caption">Loading mission outputs...</Typography>
                  </Stack>
                ) : irrigationError ? (
                  <Alert severity="warning">{irrigationError}</Alert>
                ) : irrigationSummary ? (
                  <Stack spacing={1.2}>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      <Chip
                        size="small"
                        label={`Status: ${irrigationSummary.status}`}
                        color={
                          irrigationSummary.status === "completed"
                            ? "success"
                            : irrigationSummary.status === "failed"
                              ? "error"
                              : "default"
                        }
                      />
                      <Chip
                        size="small"
                        label={`Captures: ${irrigationSummary.capture_count}`}
                        variant="outlined"
                      />
                      <Chip
                        size="small"
                        label={`Dry: ${
                          irrigationSummary.summary?.counts_by_type?.under_irrigated ?? 0
                        }`}
                        variant="outlined"
                      />
                      <Chip
                        size="small"
                        label={`Overwatered: ${
                          irrigationSummary.summary?.counts_by_type?.overwatered ?? 0
                        }`}
                        variant="outlined"
                      />
                      <Chip
                        size="small"
                        label={`Bands: ${
                          irrigationSummary.summary?.counts_by_type?.uneven_distribution ?? 0
                        }`}
                        variant="outlined"
                      />
                      <Chip
                        size="small"
                        label={`Avg confidence: ${(
                          Number(irrigationSummary.summary?.average_confidence ?? 0) * 100
                        ).toFixed(0)}%`}
                        variant="outlined"
                      />
                    </Stack>

                    {irrigationSummary.layer?.error && (
                      <Alert severity="error">{irrigationSummary.layer.error}</Alert>
                    )}

                    {!irrigationSummary.capture_count ? (
                      <Alert severity="info">
                        No geotagged captures have been ingested for this mission yet.
                      </Alert>
                    ) : (
                      <Typography variant="caption" component="div">
                        Latest mission: {trackedMissionId}. The stitched preview overlay, anomaly
                        polygons, and ranked inspection points appear on the map when processing
                        completes.
                      </Typography>
                    )}

                    {irrigationCapturePreview.length > 0 && (
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        {irrigationCapturePreview.map((capture) => (
                          <Chip
                            key={capture.id}
                            size="small"
                            label={`#${capture.id} @ ${capture.lat.toFixed(4)}, ${capture.lon.toFixed(
                              4
                            )}`}
                            variant="outlined"
                          />
                        ))}
                      </Stack>
                    )}

                    {(irrigationSummary.inspection_points ?? []).slice(0, 3).map((point, index) => (
                      <Typography key={point.id} variant="caption" component="div">
                        {index + 1}. {point.label} at {point.lat.toFixed(5)}, {point.lon.toFixed(5)}
                      </Typography>
                    ))}
                  </Stack>
                ) : (
                  <Alert severity="info">Run a grid mission to generate irrigation outputs.</Alert>
                )}
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
    </>
  );
}
