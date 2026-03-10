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
  LinearProgress,

} from "@mui/material";
import Header from "../../../components/dashboard/Header";
import InfoLabel from "../../../components/dashboard/InfoLabel";
import type { TerraDraw } from "terra-draw";
import {
  Polyline,
  Polygon,
  OverlayView,
} from "@react-google-maps/api";
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
type PhotogrammetryProfile = {
  front_overlap_pct: number;
  side_overlap_pct: number;
  fixed_exposure: boolean;
  trigger_mode: "distance" | "time";
  trigger_distance_m: number;
  trigger_interval_s: number;
  speed_mps: number;
  positioning: "standard_gnss" | "rtk_ppk";
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
type MappingAssetRecord = {
  id: number;
  type: string;
  url: string;
  meta_data?: Record<string, unknown>;
  created_at?: string;
};
type MappingJobRecord = {
  job_id: number;
  field_id: number;
  model_id: number;
  status: "pending" | "uploading" | "processing" | "ready" | "failed";
  progress: number;
  error?: string | null;
  processor: string;
  processor_task_id?: string | null;
  assets: MappingAssetRecord[];
};

const MAX_GRID_PREVIEW_WAYPOINTS = 2200;
const GRID_PREVIEW_DEBOUNCE_MS = 250;
const CESIUM_MAX_SAFE_ZOOM = 16;
const PHOTOGRAMMETRY_ALT_MIN_M = 20;
const PHOTOGRAMMETRY_ALT_MAX_M = 30;
const INFO_INPUT_LABEL_PROPS = {
  shrink: true,
  sx: { pointerEvents: "auto" },
} as const;

export default function PhotoGrammetryPage() {
  const [fieldName, setFieldName] = useState("Field A");
  const [fieldBorder, setFieldBorder] = useState<LonLat[] | null>(null);
  const [fields, setFields] = useState<FieldFeature[]>([]);
  const [loadingFields, setLoadingFields] = useState(false);
  const [selectedFieldId, setSelectedFieldId] = useState<number | null>(null);
  const [fieldsRefreshNonce, setFieldsRefreshNonce] = useState(0);
  const [savingField, setSavingField] = useState(false);
  const [deletingField, setDeletingField] = useState(false);
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
  const [alt, setAlt] = useState(25);
  const [altInput, setAltInput] = useState("25");
  const [name, setName] = useState("photogrammetry-plan-1");
  const [sending, setSending] = useState(false);
  const [preflightRun, setPreflightRun] =
    useState<PreflightRunResponse | null>(null);
  const [gridParams, setGridParams] = useState<GridParams>({
    row_spacing_m: 7.5,
    grid_angle_deg: null,
    slope_aware: false,
    safety_inset_m: 1.5,
    terrain_follow: false,
    agl_m: 25,
    pattern_mode: "boustrophedon",
    crosshatch_angle_offset_deg: 90,
    start_corner: "auto",
    lane_strategy: "serpentine",
    row_stride: 1,
    row_phase_m: 0,
  });
  const [photogrammetryProfile, setPhotogrammetryProfile] =
    useState<PhotogrammetryProfile>({
      front_overlap_pct: 80,
      side_overlap_pct: 70,
      fixed_exposure: true,
      trigger_mode: "distance",
      trigger_distance_m: 2.5,
      trigger_interval_s: 1.0,
      speed_mps: 3.0,
      positioning: "rtk_ppk",
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
  const [mappingInputMode, setMappingInputMode] = useState<"upload" | "drone_sync">(
    "upload"
  );
  const [mappingInputFiles, setMappingInputFiles] = useState<File[]>([]);
  const [mappingSyncSourceDir, setMappingSyncSourceDir] = useState("");
  const [mappingBusy, setMappingBusy] = useState(false);
  const [mappingError, setMappingError] = useState<string | null>(null);
  const [mappingJobStatus, setMappingJobStatus] = useState<MappingJobRecord | null>(
    null
  );
  const [activeMappingJobId, setActiveMappingJobId] = useState<number | null>(
    null
  );
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
      setWaypoints((prev) => [...prev, { lat: p.lat, lon: p.lng, alt }]);
    },
    [alt]
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

  useEffect(() => {
    setMappingError(null);
    setMappingJobStatus(null);
    setActiveMappingJobId(null);
    setFieldTilesetUrl(null);
  }, [selectedFieldId]);

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

  const deleteSelectedField = useCallback(async () => {
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
    const confirmed = window.confirm(
      `Delete field "${targetField?.name ?? `#${selectedFieldId}`}"? This cannot be undone.`
    );
    if (!confirmed) return;

    setDeletingField(true);
    try {
      const res = await fetch(`${API_BASE_CLEAN}/fields/${selectedFieldId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || "Failed to delete field");
      }

      setFields((prev) => prev.filter((f) => f.id !== selectedFieldId));
      clearFieldBorder();
      setFieldName("Field A");
      alert(`Deleted field "${targetField?.name ?? `#${selectedFieldId}`}"`);
    } catch (e: any) {
      addError(e?.message ?? "Failed to delete field");
    } finally {
      setDeletingField(false);
    }
  }, [API_BASE_CLEAN, addError, fields, selectedFieldId]);

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

  const resolveTilesetUrlFromAssets = useCallback(
    async (assets: MappingAssetRecord[] | undefined): Promise<string | null> => {
      if (!Array.isArray(assets)) return null;
      const tilesetAsset = assets.find(
        (asset) => asset?.type === "TILESET_3D" && typeof asset?.url === "string"
      );
      if (!tilesetAsset?.url) return null;

      const token = getToken();
      if (token && Number.isFinite(tilesetAsset.id)) {
        try {
          const signedRes = await fetch(
            `${API_BASE_CLEAN}/mapping/assets/${tilesetAsset.id}/signed-url?ttl_seconds=3600&path=tileset.json`,
            { headers: { Authorization: `Bearer ${token}` } }
          );
          if (signedRes.ok) {
            const signedData = (await signedRes.json()) as { url?: string };
            if (typeof signedData?.url === "string" && signedData.url.trim().length > 0) {
              return signedData.url;
            }
          }
        } catch {
          // Fallback to direct static URL when signed URL is unavailable.
        }
      }

      const absolute = toAbsoluteAssetUrl(tilesetAsset.url);
      if (/\.json(\?|$)/i.test(absolute)) {
        return absolute;
      }
      return `${absolute.replace(/\/+$/, "")}/tileset.json`;
    },
    [API_BASE_CLEAN, toAbsoluteAssetUrl]
  );

  const fetchMappingJobStatus = useCallback(
    async (jobId: number): Promise<MappingJobRecord | null> => {
      const token = getToken();
      if (!token) return null;

      const res = await fetch(`${API_BASE_CLEAN}/mapping/jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || `Failed to fetch mapping job ${jobId}`);
      }

      const data = (await res.json()) as MappingJobRecord;
      setMappingJobStatus(data);
      setMappingError(data.error ?? null);

      if (data.status === "ready") {
        const tilesetUrl = await resolveTilesetUrlFromAssets(data.assets);
        if (tilesetUrl) {
          setFieldTilesetUrl(tilesetUrl);
        }
        setUseCesium(true);
        setCesiumViewMode("top");
        setActiveMappingJobId(null);
      } else if (data.status === "failed") {
        setActiveMappingJobId(null);
      }

      return data;
    },
    [API_BASE_CLEAN, resolveTilesetUrlFromAssets]
  );

  useEffect(() => {
    if (activeMappingJobId == null) return;

    let cancelled = false;
    const tick = async () => {
      try {
        await fetchMappingJobStatus(activeMappingJobId);
      } catch (e: any) {
        if (!cancelled) {
          setMappingError(e?.message ?? "Failed to refresh mapping progress");
        }
      }
    };

    void tick();
    const id = setInterval(() => {
      void tick();
    }, 3000);

    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [activeMappingJobId, fetchMappingJobStatus]);

  useEffect(() => {
    if (selectedFieldId == null) return;
    const token = getToken();
    if (!token) return;

    let cancelled = false;
    const loadLatestReady = async () => {
      try {
        const res = await fetch(
          `${API_BASE_CLEAN}/mapping/fields/${selectedFieldId}/latest-ready`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (!res.ok) return;
        const data = (await res.json()) as MappingJobRecord;
        if (cancelled) return;

        setMappingJobStatus(data);
        const tilesetUrl = await resolveTilesetUrlFromAssets(data.assets);
        if (cancelled) return;
        if (tilesetUrl) {
          setFieldTilesetUrl(tilesetUrl);
        }
      } catch {
        // Ignore preload errors; user can still create a new map.
      }
    };

    void loadLatestReady();
    return () => {
      cancelled = true;
    };
  }, [API_BASE_CLEAN, resolveTilesetUrlFromAssets, selectedFieldId]);

  const mappingJobRunning = activeMappingJobId != null;

  const create3DFieldMap = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setMappingError("Not authenticated");
      return;
    }
    if (selectedFieldId == null) {
      setMappingError("Select a saved field before creating a 3D field map.");
      return;
    }
    if (mappingInputMode === "upload" && mappingInputFiles.length === 0) {
      setMappingError("Select mapping images before starting upload-based processing.");
      return;
    }

    setMappingBusy(true);
    setMappingError(null);
    setMappingJobStatus(null);

    try {
      const createRes = await fetch(`${API_BASE_CLEAN}/mapping/jobs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          field_id: selectedFieldId,
          processor: "webodm",
          input_source: mappingInputMode,
          drone_sync:
            mappingInputMode === "drone_sync"
              ? {
                  source_dir: mappingSyncSourceDir.trim() || undefined,
                  recursive: true,
                }
              : undefined,
          start_immediately: mappingInputMode === "drone_sync",
          artifacts: {
            orthomosaic: true,
            dsm: true,
            dtm: false,
            textured_mesh: true,
            point_cloud: false,
            xyz_tiles: true,
          },
          webodm_options: {},
        }),
      });
      if (!createRes.ok) {
        const detail = await createRes.text();
        throw new Error(detail || "Failed to create mapping job");
      }

      const created = (await createRes.json()) as { job_id?: number };
      const jobId = Number(created?.job_id);
      if (!Number.isFinite(jobId) || jobId <= 0) {
        throw new Error("Mapping job was created but no valid job id was returned.");
      }

      if (mappingInputMode === "upload") {
        const formData = new FormData();
        mappingInputFiles.forEach((file) => {
          formData.append("files", file);
        });

        const uploadRes = await fetch(`${API_BASE_CLEAN}/mapping/jobs/${jobId}/images`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
        if (!uploadRes.ok) {
          const detail = await uploadRes.text();
          throw new Error(detail || "Failed to upload mapping images");
        }

        const startRes = await fetch(`${API_BASE_CLEAN}/mapping/jobs/${jobId}/start`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!startRes.ok) {
          const detail = await startRes.text();
          throw new Error(detail || "Failed to start mapping job");
        }
      }

      setActiveMappingJobId(jobId);
      await fetchMappingJobStatus(jobId);
    } catch (e: any) {
      setMappingError(e?.message ?? "Failed to create 3D field map");
    } finally {
      setMappingBusy(false);
    }
  }, [
    API_BASE_CLEAN,
    fetchMappingJobStatus,
    mappingInputFiles,
    mappingInputMode,
    mappingSyncSourceDir,
    selectedFieldId,
  ]);

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
      setWaypoints((prev) => [...prev, { lat, lon: lng, alt }]);
    },
    [alt, terraDrawMode]
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
    if (num < PHOTOGRAMMETRY_ALT_MIN_M || num > PHOTOGRAMMETRY_ALT_MAX_M) {
      addError(
        `Photogrammetry altitude must be between ${PHOTOGRAMMETRY_ALT_MIN_M} and ${PHOTOGRAMMETRY_ALT_MAX_M} meters`
      );
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
          setGridPreviewError(
            detail || `Photogrammetry coverage preview failed (HTTP ${res.status})`
          );
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
        setGridPreviewError("Photogrammetry coverage preview failed. Please try again.");
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
    if (
      !Number.isFinite(altToUse) ||
      altToUse < PHOTOGRAMMETRY_ALT_MIN_M ||
      altToUse > PHOTOGRAMMETRY_ALT_MAX_M
    ) {
      addError(
        `Photogrammetry altitude must be between ${PHOTOGRAMMETRY_ALT_MIN_M} and ${PHOTOGRAMMETRY_ALT_MAX_M} meters`
      );
      return;
    }

    if (!fieldBorder || fieldBorder.length < 3) {
      addError("Draw or select a field polygon before starting a photogrammetry mission");
      return;
    }
    if (gridPreview && gridPreview.length > MAX_GRID_PREVIEW_WAYPOINTS) {
      addError(
        `Photogrammetry coverage preview is too dense for safe execution (${gridPreview.length}/${MAX_GRID_PREVIEW_WAYPOINTS} waypoints). Increase row spacing, increase row stride, or split the field.`
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
        mission_profile: {
          type: "photogrammetry",
          altitude_m: altToUse,
          front_overlap_pct: photogrammetryProfile.front_overlap_pct,
          side_overlap_pct: photogrammetryProfile.side_overlap_pct,
          camera: {
            orientation: "nadir",
            fixed_exposure: photogrammetryProfile.fixed_exposure,
          },
          speed_mps: photogrammetryProfile.speed_mps,
          trigger:
            photogrammetryProfile.trigger_mode === "distance"
              ? {
                  mode: "distance",
                  distance_m: photogrammetryProfile.trigger_distance_m,
                }
              : {
                  mode: "time",
                  interval_s: photogrammetryProfile.trigger_interval_s,
                },
          accuracy: photogrammetryProfile.positioning,
        },
        processing: {
          service: "webodm",
          deployment: "fastapi_job_service",
          worker: {
            dedicated_machine_recommended: true,
            gpu_recommended: true,
            gpu_required: false,
          },
        },
        requested_artifacts: {
          orthomosaic: { required: true, format: "cog_geotiff" },
          dsm: { required: true, format: "cog_geotiff" },
          dtm: { required: false, format: "cog_geotiff" },
          textured_mesh: { required: true, format: "3d_tiles" },
          point_cloud: { required: false, format: "las_laz" },
        },
        grid: {
          field_polygon_lonlat: fieldBorder,
          row_spacing_m: gridParams.row_spacing_m,
          grid_angle_deg: gridParams.grid_angle_deg,
          slope_aware: gridParams.slope_aware,
          safety_inset_m: gridParams.safety_inset_m,
          terrain_follow: gridParams.terrain_follow,
          agl_m: altToUse,
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
      alert(`PhotoGrammetry Mission: "${data.mission_name}" started! Tracking flight...`);

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
            <Typography variant="h5">PhotoGrammetry Operations</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Build per-field digital twins (orthomosaic, elevation, and 3D mesh),
              then stream them into the tasking basemap.
            </Typography>
          </div>
          <MissionStatusChips droneConnected={droneConnected} wsConnected={wsConnected} />
        </Stack>

        <Paper
          variant="outlined"
          sx={{ p: 2, mb: 2, borderRadius: 2, bgcolor: "rgba(255,255,255,0.7)" }}
        >
          <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
            Digital Twin Artifacts
          </Typography>
          <Typography variant="body2" sx={{ mb: 1, color: "text.secondary" }}>
            Mission target: build a georeferenced field digital twin via
            OpenDroneMap/WebODM and publish the outputs as the React tasking map.
            3D delivery can be streamed as 3D Tiles directly or via Cesium ion.
          </Typography>
          <Stack spacing={0.5}>
            <Typography variant="caption">
              Orthomosaic (georeferenced 2D texture) delivered as COG GeoTIFF.
            </Typography>
            <Typography variant="caption">
              DSM and optional DTM delivered as COG GeoTIFF.
            </Typography>
            <Typography variant="caption">
              Textured 3D mesh (OBJ/GLTF/etc) converted to 3D Tiles for web streaming.
            </Typography>
            <Typography variant="caption">
              Optional: point cloud (LAS/LAZ) for inspection-grade detail.
            </Typography>
            <Typography variant="caption">
              Processing service: WebODM behind FastAPI as a mapping job service.
            </Typography>
            <Typography variant="caption">
              Deployment: dedicated worker machine recommended; GPU helps but is not mandatory.
            </Typography>
          </Stack>
        </Paper>

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
                                  useCesium
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

                <Tooltip title="Map view" placement="top-start">
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
                    </Tooltip>


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
                    onDeleteSelected={deleteSelectedField}
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
                    PhotoGrammetry Mission Parameters
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
                          photogrammetry coverage preview.
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
                            label={`${gridPreview.length} capture waypoints previewed`}
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
                          Coverage preview is too dense ({gridPreview?.length}/
                          {MAX_GRID_PREVIEW_WAYPOINTS} waypoints). Increase row
                          spacing or row stride before starting the mission.
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

                <MissionVideoPanel
                  title="PhotoGrammetry Camera"
                  imgAlt="Photogrammetry camera stream"
                  disconnectedMessage="Connect the drone to view the photogrammetry stream."
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
                    missionType="photogrammetry"
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

                  <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                    <Typography variant="subtitle2">3D Field Map Workflow</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                      1) Select a saved field polygon. 2) Create 3D map from uploaded images or direct drone sync.
                      3) Wait for processing. 4) Plan spray routes in 3D mode.
                    </Typography>

                    <Stack spacing={1.2} sx={{ mt: 1 }}>
                      <TextField variant="filled"
                        select
                        size="small"
                        label="Input source"
                        value={mappingInputMode}
                        onChange={(e) => {
                          const mode = e.target.value as "upload" | "drone_sync";
                          setMappingInputMode(mode);
                          if (mode === "drone_sync") setMappingInputFiles([]);
                        }}
                      >
                        <MenuItem value="upload">Upload Images</MenuItem>
                        <MenuItem value="drone_sync">Direct Drone Sync</MenuItem>
                      </TextField>

                      {mappingInputMode === "upload" && (
                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                          <Button variant="outlined" component="label" size="small">
                            Select Images
                            <input
                              hidden
                              multiple
                              type="file"
                              accept="image/*,.jpg,.jpeg,.png,.tif,.tiff"
                              onChange={(e) => {
                                const files = e.target.files ? Array.from(e.target.files) : [];
                                setMappingInputFiles(files);
                              }}
                            />
                          </Button>
                          <Chip
                            size="small"
                            color={mappingInputFiles.length > 0 ? "success" : "default"}
                            label={`${mappingInputFiles.length} file(s)`}
                          />
                        </Stack>
                      )}

                      {mappingInputMode === "drone_sync" && (
                        <TextField variant="filled"
                          size="small"
                          label={
                            <InfoLabel
                              label="Sync source folder (optional)"
                              info="If blank, backend tries auto-discovery in configured drone sync directory."
                            />
                          }
                          InputLabelProps={INFO_INPUT_LABEL_PROPS}
                          value={mappingSyncSourceDir}
                          onChange={(e) => setMappingSyncSourceDir(e.target.value)}
                          placeholder="field_12 or /mnt/gs-sync/field_12"
                        />
                      )}

                      <Button
                        variant="contained"
                        color="primary"
                        onClick={create3DFieldMap}
                        disabled={
                          mappingBusy ||
                          mappingJobRunning ||
                          selectedFieldId == null ||
                          (mappingInputMode === "upload" && mappingInputFiles.length === 0)
                        }
                      >
                        {mappingBusy ? "Creating 3D Field Map..." : "Create 3D Field Map"}
                      </Button>

                      {selectedFieldId == null && (
                        <Alert severity="info" sx={{ py: 0.5 }}>
                          Save/select a field first. Mapping jobs are linked to saved field IDs.
                        </Alert>
                      )}

                      {mappingError && (
                        <Alert severity="error" sx={{ py: 0.5 }}>
                          {mappingError}
                        </Alert>
                      )}

                      {mappingJobStatus && (
                        <Box>
                          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", rowGap: 1, mb: 0.5 }}>
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`Job #${mappingJobStatus.job_id}`}
                            />
                            <Chip
                              size="small"
                              color={
                                mappingJobStatus.status === "ready"
                                  ? "success"
                                  : mappingJobStatus.status === "failed"
                                  ? "error"
                                  : "warning"
                              }
                              label={mappingJobStatus.status}
                            />
                            <Chip size="small" label={`${mappingJobStatus.progress}%`} />
                          </Stack>
                          <LinearProgress
                            variant="determinate"
                            value={Math.max(0, Math.min(100, mappingJobStatus.progress))}
                          />
                          {mappingJobRunning && mappingJobStatus.status !== "ready" && mappingJobStatus.status !== "failed" && (
                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                              Processing is active. You can continue route planning once status is ready.
                            </Typography>
                          )}
                          {mappingJobStatus.status === "ready" && (
                            <Alert severity="success" sx={{ mt: 1, py: 0.5 }}>
                              3D field map is ready. Mesh + boundary are loaded for route planning.
                              <Button
                                size="small"
                                sx={{ ml: 1 }}
                                onClick={() => {
                                  setUseCesium(true);
                                  setCesiumViewMode("top");
                                }}
                              >
                                Open 3D Planning
                              </Button>
                            </Alert>
                          )}
                        </Box>
                      )}
                    </Stack>
                  </Paper>

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
                    label="Mapping altitude (m)"
                    type="text"
                    value={altInput}
                    onChange={(e) => handleAltitudeInputChange(e.target.value)}
                    onBlur={normalizeAltitude}
                    size="small"
                    fullWidth
                    inputProps={{ inputMode: "numeric", pattern: "\\d*" }}
                    error={
                      altInput !== "" &&
                      (Number(altInput) < PHOTOGRAMMETRY_ALT_MIN_M ||
                        Number(altInput) > PHOTOGRAMMETRY_ALT_MAX_M)
                    }
                    helperText={
                      altInput !== "" &&
                      (Number(altInput) < PHOTOGRAMMETRY_ALT_MIN_M ||
                        Number(altInput) > PHOTOGRAMMETRY_ALT_MAX_M)
                        ? `Recommended capture range is ${PHOTOGRAMMETRY_ALT_MIN_M}–${PHOTOGRAMMETRY_ALT_MAX_M}m`
                        : `High-res mapping profile: ${PHOTOGRAMMETRY_ALT_MIN_M}–${PHOTOGRAMMETRY_ALT_MAX_M}m`
                    }
                  />

                  <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      Mapping Mission Profile
                    </Typography>
                    <Box
                      sx={{
                        display: "grid",
                        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                        gap: 1,
                      }}
                    >
                      <TextField variant="filled"
                        size="small"
                        label="Front overlap (%)"
                        type="number"
                        value={photogrammetryProfile.front_overlap_pct}
                        onChange={(e) => {
                          const value = Number(e.target.value);
                          if (!Number.isFinite(value)) return;
                          setPhotogrammetryProfile((p) => ({
                            ...p,
                            front_overlap_pct: Math.min(85, Math.max(75, value)),
                          }));
                        }}
                        inputProps={{ min: 75, max: 85, step: 1 }}
                      />
                      <TextField variant="filled"
                        size="small"
                        label="Side overlap (%)"
                        type="number"
                        value={photogrammetryProfile.side_overlap_pct}
                        onChange={(e) => {
                          const value = Number(e.target.value);
                          if (!Number.isFinite(value)) return;
                          setPhotogrammetryProfile((p) => ({
                            ...p,
                            side_overlap_pct: Math.min(75, Math.max(65, value)),
                          }));
                        }}
                        inputProps={{ min: 65, max: 75, step: 1 }}
                      />
                      <TextField variant="filled"
                        size="small"
                        label={
                          <InfoLabel
                            label="Speed (m/s)"
                            info="Slow flight helps reduce motion blur."
                          />
                        }
                        InputLabelProps={INFO_INPUT_LABEL_PROPS}
                        type="number"
                        value={photogrammetryProfile.speed_mps}
                        onChange={(e) => {
                          const value = Number(e.target.value);
                          if (!Number.isFinite(value)) return;
                          setPhotogrammetryProfile((p) => ({
                            ...p,
                            speed_mps: Math.min(8, Math.max(1, value)),
                          }));
                        }}
                        inputProps={{ min: 1, max: 8, step: 0.1 }}
                      />
                      <TextField variant="filled"
                        select
                        size="small"
                        label="Trigger mode"
                        value={photogrammetryProfile.trigger_mode}
                        onChange={(e) =>
                          setPhotogrammetryProfile((p) => ({
                            ...p,
                            trigger_mode: e.target.value as PhotogrammetryProfile["trigger_mode"],
                          }))
                        }
                      >
                        <MenuItem value="distance">Distance-based</MenuItem>
                        <MenuItem value="time">Time-based</MenuItem>
                      </TextField>
                      {photogrammetryProfile.trigger_mode === "distance" ? (
                        <TextField variant="filled"
                          size="small"
                          label="Trigger distance (m)"
                          type="number"
                          value={photogrammetryProfile.trigger_distance_m}
                          onChange={(e) => {
                            const value = Number(e.target.value);
                            if (!Number.isFinite(value)) return;
                            setPhotogrammetryProfile((p) => ({
                              ...p,
                              trigger_distance_m: Math.min(20, Math.max(0.5, value)),
                            }));
                          }}
                          inputProps={{ min: 0.5, max: 20, step: 0.1 }}
                        />
                      ) : (
                        <TextField variant="filled"
                          size="small"
                          label="Trigger interval (s)"
                          type="number"
                          value={photogrammetryProfile.trigger_interval_s}
                          onChange={(e) => {
                            const value = Number(e.target.value);
                            if (!Number.isFinite(value)) return;
                            setPhotogrammetryProfile((p) => ({
                              ...p,
                              trigger_interval_s: Math.min(10, Math.max(0.2, value)),
                            }));
                          }}
                          inputProps={{ min: 0.2, max: 10, step: 0.1 }}
                        />
                      )}
                      <TextField variant="filled"
                        select
                        size="small"
                        label="Accuracy option"
                        value={photogrammetryProfile.positioning}
                        onChange={(e) =>
                          setPhotogrammetryProfile((p) => ({
                            ...p,
                            positioning: e.target.value as PhotogrammetryProfile["positioning"],
                          }))
                        }
                      >
                        <MenuItem value="rtk_ppk">RTK/PPK</MenuItem>
                        <MenuItem value="standard_gnss">Standard GNSS</MenuItem>
                      </TextField>
                    </Box>
                    <FormControlLabel
                      sx={{ mt: 0.5 }}
                      control={
                        <Switch
                          size="small"
                          checked={photogrammetryProfile.fixed_exposure}
                          onChange={(e) =>
                            setPhotogrammetryProfile((p) => ({
                              ...p,
                              fixed_exposure: e.target.checked,
                            }))
                          }
                        />
                      }
                      label={<Typography variant="caption">Camera: nadir + fixed exposure (recommended)</Typography>}
                    />
                  </Paper>

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
                      Number(altInput) < PHOTOGRAMMETRY_ALT_MIN_M ||
                      Number(altInput) > PHOTOGRAMMETRY_ALT_MAX_M ||
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
                        Starting PhotoGrammetry...
                      </>
                    ) : (
                      "Start PhotoGrammetry"
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
