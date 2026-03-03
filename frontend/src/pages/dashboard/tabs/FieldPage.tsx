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
} from "@mui/material";
import Header from "../../../components/dashboard/Header";
import InfoLabel from "../../../components/dashboard/InfoLabel";
import {
  TerraDraw,
  TerraDrawSelectMode,
  TerraDrawPolygonMode,
  TerraDrawLineStringMode,
  TerraDrawPointMode,
  TerraDrawRectangleMode,
  TerraDrawCircleMode,
  TerraDrawFreehandMode,
} from "terra-draw";
import { TerraDrawGoogleMapsAdapter } from "terra-draw-google-maps-adapter";
import {
  GoogleMap,
  Polyline,
  Polygon,
  OverlayView,
} from "@react-google-maps/api";
import { getToken } from "../../../auth";
import DroneSvg from "../../../assets/Drone.svg?react";
import SvgIcon from "@mui/material/SvgIcon";
import RoomIcon from "@mui/icons-material/Room";
import useTelemetryWebSocket from "../../../hooks/useTelemetryWebsocket";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import CesiumMap from "../../../utils/CesiumMap";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import { GoogleMapsContext } from "../../../utils/googleMaps";
import ChangeHistoryOutlinedIcon from "@mui/icons-material/ChangeHistoryOutlined";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import CropSquareOutlinedIcon from "@mui/icons-material/CropSquareOutlined";
import RadioButtonUncheckedOutlinedIcon from "@mui/icons-material/RadioButtonUncheckedOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import PanToolAltOutlinedIcon from "@mui/icons-material/PanToolAltOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";

type LatLng = { lat: number; lng: number };
type Waypoint = { lat: number; lon: number; alt: number };
type CesiumViewMode = "top" | "tilted" | "follow" | "fpv" | "orbit";
type DrawMode = "none" | "point" | "polyline" | "polygon";
type TerraDrawEditorMode =
  | "polygon"
  | "linestring"
  | "point"
  | "rectangle"
  | "circle"
  | "freehand"
  | "select"
  | "static";
type TerraDrawToolMode = Exclude<TerraDrawEditorMode, "static">;
type LonLat = [number, number];
type TerraFeature = {
  id?: string | number;
  properties?: Record<string, unknown>;
  geometry?: {
    type?: string;
    coordinates?: unknown;
  };
};
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
const INFO_INPUT_LABEL_PROPS = {
  shrink: true,
  sx: {
    pointerEvents: "auto",
    px: 0.5,
    backgroundColor: "background.paper",
    borderRadius: 0.5,
    lineHeight: 1.2,
  },
} as const;

function extractLatLng(value: any): LatLng | null {
  if (!value) return null;
  const lat =
    value.lat ??
    value.latitude ??
    value.Lat ??
    value.Latitude ??
    (value.position
      ? value.position.lat ?? value.position.latitude
      : undefined);
  const lon =
    value.lon ??
    value.lng ??
    value.longitude ??
    value.Lon ??
    value.Lng ??
    value.Longitude ??
    (value.position
      ? value.position.lon ??
        value.position.lng ??
        value.position.longitude
      : undefined);
  if (typeof lat !== "number" || typeof lon !== "number") return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (lat < -90 || lat > 90) return null;
  if (lon < -180 || lon > 180) return null;
  return { lat, lng: lon };
}

export default function FieldPage() {
  const [fieldName, setFieldName] = useState("Field A");
  const [fieldBorder, setFieldBorder] = useState<LonLat[] | null>(null);
  const [fields, setFields] = useState<FieldFeature[]>([]);
  const [loadingFields, setLoadingFields] = useState(false);
  const [selectedFieldId, setSelectedFieldId] = useState<number | null>(null);
  const [fieldsRefreshNonce, setFieldsRefreshNonce] = useState(0);
  const [savingField, setSavingField] = useState(false);
  const [deletingField, setDeletingField] = useState(false);
  const [autoStartOnFieldSelect, setAutoStartOnFieldSelect] = useState(false);
  const [pendingAutoStartForFieldId, setPendingAutoStartForFieldId] = useState<
    number | null
  >(null);
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
    setPendingAutoStartForFieldId(null);
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
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeFlightIdRef = useRef<string | null>(null);
  const missionStartAtRef = useRef<number | null>(null);
  const missionLaunchInFlightRef = useRef(false);
  const gridPreviewAbortRef = useRef<AbortController | null>(null);
  const rafRef = useRef<number | null>(null);
  const lastPanRef = useRef(0);
  const snappedToDroneRef = useRef(false);
  const [userCenter, setUserCenter] = useState<LatLng | null>(null);
  const [droneCenter, setDroneCenter] = useState<LatLng | null>(null);
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const [alt, setAlt] = useState(30);
  const [altInput, setAltInput] = useState("30");
  const [name, setName] = useState("field-plan-1");
  const [sending, setSending] = useState(false);
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
  const videoStartedRef = useRef(false);
  const [activeFlightId, setActiveFlightId] = useState<string | null>(null);
  const [missionStatus, setMissionStatus] = useState<MissionStatus | null>(
    null
  );
  const [exclusionZones, setExclusionZones] = useState<LonLat[][]>([]);
  const [fieldTilesetUrl, setFieldTilesetUrl] = useState<string | null>(null);
  const [mapZoom, setMapZoom] = useState(12);
  const [streamKey, setStreamKey] = useState(Date.now());
  const [startingVideo, setStartingVideo] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
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
  const wsEnabled = Boolean(
    missionStatus?.orchestrator?.drone_connected &&
      missionStatus?.telemetry?.running &&
      activeFlightId
  );

  const handleCesiumPick = useCallback(
    (p: { lat: number; lng: number }) => {
      setWaypoints((prev) => [...prev, { lat: p.lat, lon: p.lng, alt }]);
    },
    [alt]
  );

  const { telemetry, isConnected: wsConnected, disconnect } = useTelemetryWebSocket({
    enabled: wsEnabled,
  });

  const droneConnected = Boolean(
    missionStatus?.orchestrator?.drone_connected || wsConnected
  );
  const droneReady = Boolean(wsConnected && droneCenter);

  const { isLoaded, loadError } = useContext(GoogleMapsContext);

  useEffect(() => {
    activeFlightIdRef.current = activeFlightId;
  }, [activeFlightId]);

// ✅ Define addError FIRST
const addError = useCallback((error: string) => {
  setErrors((prev) => [...prev.slice(-4), error]);
}, []);



// ✅ Then define onMapLoad (which depends on addError)
const onMapLoad = useCallback((map: google.maps.Map) => {
  mapRef.current = map;
  setMapReady(true);

  map.addListener("projection_changed", () => {
    if (terraDrawRef.current) return;

    try {
      const adapter = new TerraDrawGoogleMapsAdapter({
        map,
        lib: google.maps,
        coordinatePrecision: 9,
      });

      const draw = new TerraDraw({
        adapter,
        modes: [
          new TerraDrawSelectMode({
            flags: {
              polygon: {
                feature: {
                  draggable: true,
                  coordinates: { draggable: true, deletable: true, midpoints: true },
                },
              },
              linestring: {
                feature: {
                  draggable: true,
                  coordinates: { draggable: true, deletable: true, midpoints: true },
                },
              },
              point: { feature: { draggable: true } },
            },
          }),
          new TerraDrawPolygonMode({
            editable: true,
            showCoordinatePoints: false,
            styles: {
              fillColor: "#000000",
              fillOpacity: 0.1,
              outlineColor: "#1976d2",
              // Hide the numbered vertex dots shown while drawing
              closingPointWidth: 0,
              closingPointOutlineWidth: 0,
              coordinatePointWidth: 0,
              coordinatePointOutlineWidth: 0,
            },
          }),
          new TerraDrawLineStringMode({
            editable: true,
            showCoordinatePoints: false,
            styles: {
              lineStringColor: "#1976d2",
              closingPointWidth: 0,
              closingPointOutlineWidth: 0,
              coordinatePointWidth: 0,
              coordinatePointOutlineWidth: 0,
            },
          }),
          new TerraDrawPointMode({ editable: true, styles: { pointColor: "#1976d2" } }),
          new TerraDrawRectangleMode({ styles: { fillColor: "#000000", fillOpacity: 0.1, outlineColor: "#1976d2" } }),
          new TerraDrawCircleMode({ styles: { fillColor: "#000000", fillOpacity: 0.1, outlineColor: "#1976d2" } }),
          new TerraDrawFreehandMode({ styles: { fillColor: "#000000", fillOpacity: 0.1, outlineColor: "#1976d2" } }),
        ],
      });

      // Register listener BEFORE start() — TerraDraw has no "ready" event.
      draw.on("change", (_ids: Array<string | number>, event: string) => {
        if (
          event === "create" ||
          event === "update" ||
          event === "delete" ||
          event === "created" ||
          event === "updated" ||
          event === "deleted"
        ) {
          const snapshot = draw.getSnapshot();
          syncFieldBorderFromSnapshot(snapshot);
        }
      });

      draw.start();

      // Assign ref and mark ready synchronously right after start()
      terraDrawRef.current = draw;
      setTerraDrawReady(true);

    } catch (error) {
      console.error("Failed to initialize TerraDraw:", error);
      addError("Failed to initialize drawing tools"); // ✅ Now addError is available!
    }
  });
}, [addError, syncFieldBorderFromSnapshot]);


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
      if (autoStartOnFieldSelect) {
        setPendingAutoStartForFieldId(f.id);
      }
    },
    [autoStartOnFieldSelect, focusRingOnMap, loadRingIntoEditor]
  );

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

  const clearErrors = useCallback(() => {
    setErrors([]);
  }, []);

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
    if (!activeFlightId) {
      videoStartedRef.current = false;
    }
  }, [activeFlightId]);

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
        }`
      );
    }
  }, [API_BASE_CLEAN, addError]);

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
useEffect(() => {
  const modeMap: Record<string, any> = {
    "polygon": "polygon",
    "polyline": "linestring",
    "point": "point",
    "none": "static",
  };

  const tdMode = modeMap[drawMode];
  if (tdMode && terraDrawRef.current && terraDrawReady) {
    terraDrawRef.current.setMode(tdMode);
    setTerraDrawMode(tdMode);
  }
}, [drawMode, terraDrawReady]);

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      disconnect();
      if (terraDrawRef.current) {
            terraDrawRef.current.stop();
            terraDrawRef.current = null;
          }
    };
  }, [disconnect]);

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

  useEffect(() => {
    if (!mapRef.current || !droneCenter || !wsConnected) return;
    const now = Date.now();
    if (now - lastPanRef.current < 500) return;
    lastPanRef.current = now;

    const currentZoom = mapRef.current.getZoom() ?? 0;
    if (currentZoom < 16) return;

    mapRef.current.panTo(droneCenter);
  }, [droneCenter, wsConnected]);

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
    [API_BASE_CLEAN, fieldBorder, gridParams]
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

      const missionRes = await fetch(`${API_BASE_CLEAN}/tasks/missions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!missionRes.ok) {
        const error = await missionRes.text();
        if (missionRes.status === 409) {
          throw new Error(
            "Another mission is already running. Wait for completion before starting a new survey."
          );
        }
        throw new Error(error || "Failed to create flight plan");
      }

      const data = await missionRes.json();
      alert(`Grid Survey: "${data.mission_name}" started! Tracking flight...`);

      setActiveFlightId(data.flight_id);
      missionStartAtRef.current = Date.now();

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

  useEffect(() => {
    if (!autoStartOnFieldSelect) return;
    if (pendingAutoStartForFieldId == null) return;
    if (selectedFieldId !== pendingAutoStartForFieldId) return;
    if (!fieldBorder || fieldBorder.length < 3) return;
    if (sending) return;

    setPendingAutoStartForFieldId(null);
    const selectedName =
      fields.find((f) => f.id === selectedFieldId)?.name ??
      `#${String(selectedFieldId)}`;
    const confirmed = window.confirm(
      `Start grid survey for "${selectedName}" now with current grid parameters?`
    );
    if (!confirmed) return;
    void sendMission();
  }, [
    autoStartOnFieldSelect,
    fieldBorder,
    fields,
    pendingAutoStartForFieldId,
    selectedFieldId,
    sending,
  ]);

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

  const mapCenter = useMemo(() => {
    if (waypoints.length > 0) {
      return { lat: waypoints[0].lat, lng: waypoints[0].lon };
    }
    if (fieldBorder && fieldBorder.length > 0) {
      const [lon, lat] = fieldBorder[0];
      return { lat, lng: lon };
    }
    return userCenter || center;
  }, [fieldBorder, waypoints, userCenter, center]);

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
    telemetry?.status?.heading ??
    telemetry?.heading ??
    telemetry?.yaw ??
    null;
  const mode =
    telemetry?.status?.mode ??
    telemetry?.mode ??
    telemetry?.flight_mode ??
    null;
  const sats = telemetry?.gps?.satellites ?? telemetry?.satellites ?? null;
  const hdop =
    telemetry?.gps?.hdop ??
    telemetry?.hdop ??
    telemetry?.gps_hdop ??
    null;
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
    ? batteryCells
        .map((v) => `${formatMaybeNumber(Number(v), 2)}V`)
        .join(" / ")
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
          <div>
            <Typography variant="h5">Field Operations</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Configure field routes, stream telemetry, and monitor imagery in
              real time.
            </Typography>
          </div>
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
                      <Typography sx={{ ml: 2 }}>
                        Loading your location...
                      </Typography>
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
                  ) : useCesium ? (
                    <CesiumMap
                      center={mapCenter}
                      zoom={mapZoom}
                      viewMode={cesiumViewMode}
                      waypoints={waypoints}
                      fieldBoundary={cesiumFieldBoundary}
                      plannedRoute={cesiumPlannedRoute}
                      exclusionZones={exclusionZones}
                      fieldTilesetUrl={fieldTilesetUrl}
                      planningAltitudeM={alt}
                      lockCameraToPlanningAltitude
                      droneCenter={droneCenter}
                      headingDeg={typeof heading === "number" ? heading : null}
                      onPickLatLng={handleCesiumPick}
                      drawMode={drawMode}
                      onDrawComplete={(res) => {
                        console.log(res);
                        setDrawMode("none");
                      }}
                    />
                  ) : (
                    <Box sx={{ position: "relative" }}>
                      <GoogleMap
                        mapContainerStyle={containerStyle}
                        center={mapCenter}
                        zoom={mapZoom}
                        onClick={onMapClick}
                        onLoad={onMapLoad}
                        onUnmount={onMapUnmount}
                        onZoomChanged={onMapZoomChanged}
                        onCenterChanged={onMapCenterChanged}
                        options={mapOptions}
                      >
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
                      </GoogleMap>
                      <Paper
                        elevation={2}
                        sx={{
                          position: "absolute",
                          left: 10,
                          top: "50%",
                          transform: "translateY(-50%)",
                          zIndex: 20,
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
                            const selected = terraDrawMode === tool.mode;
                            return (
                              <Tooltip key={tool.mode} title={tool.label} placement="right" arrow>
                                <span>
                                  <IconButton
                                    size="small"
                                    onClick={() => {
                                      setTerraDrawMode(tool.mode as TerraDrawToolMode);
                                      if (terraDrawRef.current && terraDrawReady) {
                                        terraDrawRef.current.setMode(tool.mode);
                                      }
                                    }}
                                    disabled={!terraDrawReady || useCesium}
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
                                disabled={!terraDrawReady || useCesium}
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

                    </Box>
                  )}
                </Box>

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
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      Saved Fields
                    </Typography>
                    <TextField
                      select
                      size="small"
                      fullWidth
                      label="Saved fields (database)"
                      value={selectedFieldId == null ? "" : String(selectedFieldId)}
                      onChange={(e) => {
                        const raw = e.target.value;
                        if (!raw) {
                          clearFieldBorder();
                          return;
                        }
                        const id = Number(raw);
                        const field = fields.find((f) => f.id === id);
                        if (field) selectField(field);
                      }}
                      helperText={
                        selectedField
                          ? `Selected: ${selectedField.name} (#${selectedField.id})`
                          : "Select a saved field to load and focus it on the map."
                      }
                    >
                      <MenuItem value="">None</MenuItem>
                      {fields.map((f) => (
                        <MenuItem key={f.id} value={String(f.id)}>
                          {f.name} (#{f.id})
                        </MenuItem>
                      ))}
                    </TextField>
                    <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: "wrap" }}>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => setFieldsRefreshNonce((n) => n + 1)}
                        disabled={loadingFields}
                      >
                        Refresh
                      </Button>
                      <Button
                        size="small"
                        variant="text"
                        disabled={!selectedField}
                        onClick={() => selectedField && focusRingOnMap(selectedField.ring)}
                      >
                        Focus
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        color="error"
                        disabled={!selectedField || deletingField}
                        onClick={deleteSelectedField}
                      >
                        {deletingField ? "Deleting..." : "Delete"}
                      </Button>
                    </Stack>
                    <FormControlLabel
                      sx={{ mt: 1 }}
                      control={
                        <Switch
                          size="small"
                          checked={autoStartOnFieldSelect}
                          onChange={(e) => setAutoStartOnFieldSelect(e.target.checked)}
                        />
                      }
                      label={
                        <Typography variant="caption">
                          Auto-start survey when selecting a saved field
                        </Typography>
                      }
                    />
                  </Paper>

                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      Field Border
                    </Typography>
                    <Stack
                      direction={{ xs: "column", sm: "row" }}
                      spacing={1}
                      alignItems="center"
                      sx={{ flexWrap: "wrap" }}
                    >
                      <TextField
                        size="small"
                        label="Field name"
                        value={fieldName}
                        onChange={(e) => setFieldName(e.target.value)}
                        sx={{ minWidth: 220 }}
                      />

                      <Button
                        variant="contained"
                        onClick={selectedFieldId ? updateFieldBorder : saveFieldBorder}
                        disabled={savingField || !fieldBorder || fieldBorder.length < 3}
                      >
                        {savingField
                          ? selectedFieldId
                            ? "Updating..."
                            : "Saving..."
                          : selectedFieldId
                          ? "Update Field"
                          : "Save Field Border"}
                      </Button>

                      <Button variant="outlined" onClick={clearFieldBorder}>
                        Clear Border
                      </Button>

                      <Button
                        variant="text"
                        onClick={() => {
                          setSelectedFieldId(null);
                          setFieldName("Field A");
                          clearFieldBorder();
                        }}
                      >
                        New Field
                      </Button>

                      {fieldBorder && (
                        <>
                          <Chip label={`Points: ${fieldBorder.length}`} size="small" />
                          {metrics?.areaHa != null && (
                            <Chip
                              label={`Area: ${metrics.areaHa.toFixed(2)} ha`}
                              size="small"
                            />
                          )}
                          {metrics?.centroid && (
                            <Chip
                              label={`Centroid: ${metrics.centroid.lat.toFixed(5)}, ${metrics.centroid.lng.toFixed(5)}`}
                              size="small"
                            />
                          )}
                          {selectedField && (
                            <Chip label={`Selected: #${selectedField.id}`} size="small" />
                          )}
                        </>
                      )}
                    </Stack>

                    <Typography
                      variant="caption"
                      sx={{ display: "block", mt: 1, opacity: 0.8 }}
                    >
                      Draw a polygon on the map. We store coordinates as [lon, lat]
                      (GeoJSON order).
                    </Typography>
                  </Paper>
                </Box>

                <Divider sx={{ my: 2 }} />

                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={1}
                  alignItems="center"
                  justifyContent="space-between"
                >
                  <Typography variant="subtitle2">Existing Fields</Typography>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => setFieldsRefreshNonce((n) => n + 1)}
                    disabled={loadingFields}
                  >
                    Refresh
                  </Button>
                </Stack>

                {loadingFields ? (
                  <Box
                    sx={{ mt: 1, display: "flex", alignItems: "center", gap: 1 }}
                  >
                    <CircularProgress size={18} />
                    <Typography variant="body2">Loading fields…</Typography>
                  </Box>
                ) : fields.length === 0 ? (
                  <Typography variant="body2" sx={{ mt: 1, opacity: 0.8 }}>
                    No fields saved yet.
                  </Typography>
                ) : (
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ mt: 1, flexWrap: "wrap", rowGap: 1 }}
                  >
                    {fields.map((f) => (
                      <Chip
                        key={f.id}
                        label={`${f.name} (#${f.id})`}
                        variant={selectedFieldId === f.id ? "filled" : "outlined"}
                        color={selectedFieldId === f.id ? "primary" : "default"}
                        onClick={() => selectField(f)}
                        sx={{ cursor: "pointer" }}
                      />
                    ))}
                  </Stack>
                )}

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
                      <TextField
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
                      <TextField
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
                      <TextField
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
                      <TextField
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
                      <TextField
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
                      <TextField
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
                      <TextField
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
                        <TextField
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
                      <TextField
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
                        <TextField
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
                  <Box
                    sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}
                  >
                    <FormControlLabel
                      control={
                        <Switch
                          checked={useCesium}
                          onChange={(e) => setUseCesium(e.target.checked)}
                        />
                      }
                      label={useCesium ? "3D (Cesium)" : "2D (Google)"}
                    />

                    {useCesium && (
                      <ToggleButtonGroup
                        value={cesiumViewMode}
                        exclusive
                        size="small"
                        onChange={(_, v) => {
                          if (!v) return;
                          setCesiumViewMode(v);
                        }}
                        aria-label="Cesium view mode"
                      >
                        <ToggleButton value="top" aria-label="Top view">
                          Top
                        </ToggleButton>
                        <ToggleButton value="tilted" aria-label="Tilted view">
                          Tilted
                        </ToggleButton>
                        <ToggleButton value="follow" aria-label="Follow drone">
                          Follow
                        </ToggleButton>
                        <ToggleButton value="fpv" aria-label="FPV view">
                          FPV
                        </ToggleButton>
                        <ToggleButton value="orbit" aria-label="Orbit view">
                          Orbit
                        </ToggleButton>
                      </ToggleButtonGroup>
                    )}
                  </Box>
                </Box>

                <Typography variant="body2" sx={{ mt: 1 }}>
                  Click on the map to add waypoints.
                </Typography>
                <Typography variant="body2" sx={{ mt: 1 }}>
                  Drone Status: {droneConnected ? "Connected" : "Disconnected"}
                  {activeFlightId &&
                    ` | Active Flight: ${activeFlightId.substring(0, 8)}...`}
                  {wsConnected && ` | WS: Connected`}
                </Typography>

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
                            <Typography
                              variant="h6"
                              sx={{ color: "warning.main", mb: 1 }}
                            >
                              ⚠️ Video Stream Unavailable
                            </Typography>
                            <Typography
                              variant="body2"
                              sx={{ color: "grey.400", mb: 2 }}
                            >
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
                              src={`${API_BASE_CLEAN}/video/mjpeg?key=${streamKey}${
                                videoToken
                                  ? `&token=${encodeURIComponent(videoToken)}`
                                  : ""
                              }`}
                              alt="Survey camera stream"
                              onError={handleVideoError}
                              onLoad={handleVideoLoad}
                              sx={{ width: "100%", height: "100%", objectFit: "cover" }}
                            />

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
                                    typeof heading === "number" &&
                                    Number.isFinite(heading)
                                      ? `${Math.round(heading)}°`
                                      : "--"
                                  }
                                />
                                <TelemetryBox
                                  label="GPS"
                                  value={
                                    sats === null || sats === undefined
                                      ? "--"
                                      : `${sats} sats`
                                  }
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
                          sx={{
                            fontWeight: 600,
                            color: failsafeActive ? "error.main" : "text.primary",
                          }}
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
                        <Typography
                          variant="body2"
                          sx={{ fontWeight: 600, textAlign: "right" }}
                        >
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
                          sx={{
                            fontWeight: 600,
                            color: failsafeActive ? "error.main" : "text.primary",
                          }}
                        >
                          {failsafeState}
                        </Typography>
                      </Stack>
                    </Stack>
                  </Paper>
                  <TextField
                    label="Mission name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    size="small"
                    fullWidth
                    required
                    error={!name.trim()}
                    helperText={!name.trim() ? "Mission name is required" : " "}
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
