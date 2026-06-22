import { useEffect, useMemo, useRef } from "react";
import "cesium/Build/Cesium/Widgets/widgets.css";
import * as Cesium from "cesium";
import {
  completeShape,
  isFlatBoundaryDrawMode,
  shapePreview,
  type ShapeDrawMode,
  type ShapeDrawResult,
} from "../../../modules/maps/utils/drawingShapes";
import { isNearLonLat } from "../utils/flatMapShapeGeometry";
import droneIconUrl from "../../../assets/Drone.svg?url";

type LatLng = { lat: number; lng: number };
type Waypoint = { lat: number; lon: number; alt: number };
type LonLat = [number, number];
export type CesiumViewMode = "top" | "tilted" | "follow" | "fpv" | "orbit";
export type DrawMode = ShapeDrawMode;
export type DrawResult = ShapeDrawResult;

type Props = {
  center: LatLng;
  zoom: number;
  viewMode: CesiumViewMode;
  waypoints: Waypoint[];
  droneCenter: LatLng | null;
  headingDeg?: number | null;
  onPickLatLng?: (p: LatLng) => void;
  drawMode?: DrawMode;
  onDrawComplete?: (res: DrawResult) => void;
  onBoundaryDrawStarted?: () => void;
  onBoundaryDrawProgress?: (coords: LonLat[]) => void;
  fieldBoundary?: LonLat[] | null;
  onFieldBoundaryClick?: () => void;
  drawnBoundarySelected?: boolean;
  plannedRoute?: LonLat[] | null;
  exclusionZones?: LonLat[][];
  fieldTilesetUrl?: string | null;
  planningAltitudeM?: number;
  lockCameraToPlanningAltitude?: boolean;
  useWorldTerrain?: boolean;
  focusRing?: LonLat[] | null;
  focusRequestToken?: number;
};
const EMPTY_ZONES: LonLat[][] = [];

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

function zoomToHeightMeters(zoom: number) {
  const z = clamp(zoom, 1, 20);
  return Math.round(20000000 / Math.pow(2, z));
}

function normalizeLonLatLine(coords: LonLat[] | null | undefined): LonLat[] {
  if (!coords || coords.length === 0) return [];
  return coords.filter(
    (p) =>
      Array.isArray(p) &&
      p.length >= 2 &&
      Number.isFinite(p[0]) &&
      Number.isFinite(p[1]),
  );
}

function normalizeLonLatRing(coords: LonLat[] | null | undefined): LonLat[] {
  const line = normalizeLonLatLine(coords);
  if (line.length < 3) return [];
  const first = line[0];
  const last = line[line.length - 1];
  if (first[0] === last[0] && first[1] === last[1]) return line.slice(0, -1);
  return line;
}

function computeRingCentroid(
  coords: LonLat[] | null | undefined,
): LatLng | null {
  const ring = normalizeLonLatRing(coords);
  if (ring.length < 3) return null;

  let twiceArea = 0;
  let cx = 0;
  let cy = 0;

  for (let i = 0; i < ring.length; i += 1) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[(i + 1) % ring.length];
    const cross = x1 * y2 - x2 * y1;
    twiceArea += cross;
    cx += (x1 + x2) * cross;
    cy += (y1 + y2) * cross;
  }

  if (Math.abs(twiceArea) < 1e-12) {
    const average = ring.reduce(
      (acc, [lng, lat]) => ({ lng: acc.lng + lng, lat: acc.lat + lat }),
      { lng: 0, lat: 0 },
    );
    return {
      lng: average.lng / ring.length,
      lat: average.lat / ring.length,
    };
  }

  return {
    lng: cx / (3 * twiceArea),
    lat: cy / (3 * twiceArea),
  };
}

function computeFieldCameraView(
  coords: LonLat[] | null | undefined,
): { center: LatLng; topHeight: number } | null {
  const ring = normalizeLonLatRing(coords);
  if (ring.length < 3) return null;

  const center = computeRingCentroid(ring);
  if (!center) return null;

  let west = Infinity;
  let east = -Infinity;
  let south = Infinity;
  let north = -Infinity;

  ring.forEach(([lng, lat]) => {
    west = Math.min(west, lng);
    east = Math.max(east, lng);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  });

  const latSpanMeters = Math.max(0, north - south) * 111_320;
  const lngScale = Math.max(0.2, Math.cos((center.lat * Math.PI) / 180));
  const lngSpanMeters = Math.max(0, east - west) * 111_320 * lngScale;
  const spanMeters = Math.max(latSpanMeters, lngSpanMeters);

  return {
    center,
    topHeight: clamp(Math.round(spanMeters * 2.4), 120, 20_000),
  };
}

export default function CesiumMap({
  center,
  zoom,
  viewMode,
  waypoints,
  droneCenter,
  headingDeg,
  onPickLatLng,
  drawMode = "none",
  onDrawComplete,
  onBoundaryDrawStarted,
  onBoundaryDrawProgress,
  fieldBoundary = null,
  onFieldBoundaryClick,
  drawnBoundarySelected = false,
  plannedRoute = null,
  exclusionZones = EMPTY_ZONES,
  fieldTilesetUrl = null,
  planningAltitudeM = 25,
  lockCameraToPlanningAltitude = false,
  useWorldTerrain = true,
  focusRing = null,
  focusRequestToken,
}: Props) {
  const drawModeRef = useRef<DrawMode>("none");
  const onDrawCompleteRef = useRef<Props["onDrawComplete"]>(onDrawComplete);
  const onBoundaryDrawStartedRef = useRef<Props["onBoundaryDrawStarted"]>(
    onBoundaryDrawStarted,
  );
  const onBoundaryDrawProgressRef = useRef<Props["onBoundaryDrawProgress"]>(
    onBoundaryDrawProgress,
  );
  const drawHandlerRef = useRef<Cesium.ScreenSpaceEventHandler | null>(null);
  const drawAnchorsRef = useRef<Cesium.Entity[]>([]);
  const drawTempEntityRef = useRef<Cesium.Entity | null>(null);
  const drawFloatingPointRef = useRef<Cesium.Entity | null>(null);
  const drawPositionsRef = useRef<Cesium.Cartesian3[]>([]);
  const drawFreehandActiveRef = useRef(false);
  const drawIsActiveRef = useRef(false);
  const drawFloatingCartesianRef = useRef<Cesium.Cartesian3 | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const CesiumRef = useRef<typeof Cesium | null>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const clickHandlerRef = useRef<Cesium.ScreenSpaceEventHandler | null>(null);
  const rafRef = useRef<number | null>(null);
  const droneEntityRef = useRef<Cesium.Entity | null>(null);
  const polylineEntityRef = useRef<Cesium.Entity | null>(null);
  const waypointPolygonEntityRef = useRef<Cesium.Entity | null>(null);
  const plannedRouteEntityRef = useRef<Cesium.Entity | null>(null);
  const fieldBoundaryEntityRef = useRef<Cesium.Entity | null>(null);
  const exclusionZoneEntityRefs = useRef<Cesium.Entity[]>([]);
  const waypointEntityRefs = useRef<Cesium.Entity[]>([]);
  const fieldTilesetRef = useRef<Cesium.Cesium3DTileset | null>(null);
  const fieldTilesetUrlRef = useRef<string | null>(fieldTilesetUrl);
  const tilesetLoadSeqRef = useRef(0);
  const onPickLatLngRef = useRef<Props["onPickLatLng"]>(onPickLatLng);
  const onFieldBoundaryClickRef = useRef<Props["onFieldBoundaryClick"]>(
    onFieldBoundaryClick,
  );
  const lastCameraSignatureRef = useRef<string | null>(null);

  useEffect(() => {
    drawModeRef.current = drawMode;
  }, [drawMode]);

  useEffect(() => {
    onDrawCompleteRef.current = onDrawComplete;
  }, [onDrawComplete]);

  useEffect(() => {
    onBoundaryDrawStartedRef.current = onBoundaryDrawStarted;
  }, [onBoundaryDrawStarted]);

  useEffect(() => {
    onBoundaryDrawProgressRef.current = onBoundaryDrawProgress;
  }, [onBoundaryDrawProgress]);

  useEffect(() => {
    onPickLatLngRef.current = onPickLatLng;
  }, [onPickLatLng]);

  useEffect(() => {
    onFieldBoundaryClickRef.current = onFieldBoundaryClick;
  }, [onFieldBoundaryClick]);

  useEffect(() => {
    fieldTilesetUrlRef.current = fieldTilesetUrl;
  }, [fieldTilesetUrl]);

  const safeHeadingRad = useMemo(() => {
    const h =
      typeof headingDeg === "number" && Number.isFinite(headingDeg)
        ? headingDeg
        : 0;
    return (h * Math.PI) / 180;
  }, [headingDeg]);

  const fieldCameraView = useMemo(
    () =>
      drawMode !== "none" ? null : computeFieldCameraView(fieldBoundary),
    [fieldBoundary, drawMode],
  );
  const hasDroneCenter = Boolean(droneCenter);
  const cameraCenterKey = hasDroneCenter
    ? `drone-live:${fieldCameraView?.center.lat.toFixed(7) ?? "none"}:${fieldCameraView?.center.lng.toFixed(7) ?? "none"}:${focusRequestToken ?? 0}`
    : `${center.lat.toFixed(7)}:${center.lng.toFixed(7)}:${focusRequestToken ?? 0}`;

  const latestValuesRef = useRef({
    droneCenter,
    center,
    safeHeadingRad,
    fieldCameraView,
  });

  const userInteractingRef = useRef(false);
  const interactionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

  useEffect(() => {
    latestValuesRef.current = {
      droneCenter,
      center,
      safeHeadingRad,
      fieldCameraView,
    };
  }, [droneCenter, center, safeHeadingRad, fieldCameraView]);

  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;

    const clearTimer = () => {
      if (interactionTimerRef.current != null) {
        clearTimeout(interactionTimerRef.current);
        interactionTimerRef.current = null;
      }
    };

    const startInteraction = () => {
      clearTimer();
      userInteractingRef.current = true;
    };

    const keepAlive = () => {
      if (!userInteractingRef.current) return;
      clearTimer();
      interactionTimerRef.current = setTimeout(() => {
        userInteractingRef.current = false;
      }, 400);
    };

    const endInteraction = () => {
      clearTimer();
      interactionTimerRef.current = setTimeout(() => {
        userInteractingRef.current = false;
      }, 400);
    };

    el.addEventListener("mousedown", startInteraction);
    el.addEventListener("touchstart", startInteraction, { passive: true });
    el.addEventListener("wheel", startInteraction, { passive: true });

    document.addEventListener("mousemove", keepAlive);
    document.addEventListener("touchmove", keepAlive, { passive: true });
    document.addEventListener("mouseup", endInteraction);
    document.addEventListener("touchend", endInteraction);
    el.addEventListener("wheel", endInteraction, { passive: true });

    return () => {
      el.removeEventListener("mousedown", startInteraction);
      el.removeEventListener("touchstart", startInteraction);
      el.removeEventListener("wheel", startInteraction);
      document.removeEventListener("mousemove", keepAlive);
      document.removeEventListener("touchmove", keepAlive);
      document.removeEventListener("mouseup", endInteraction);
      document.removeEventListener("touchend", endInteraction);
      el.removeEventListener("wheel", endInteraction);
      clearTimer();
    };
  }, []);

  const viewerReadyRef = useRef(false);

  function updateDroneEntity() {
    const CesiumModule = CesiumRef.current;
    const viewer = viewerRef.current;
    if (!CesiumModule || !viewer) return;

    const dc = latestValuesRef.current.droneCenter;
    if (!dc) {
      if (droneEntityRef.current) {
        viewer.entities.remove(droneEntityRef.current);
        droneEntityRef.current = null;
      }
      return;
    }

    const markerHeightM = clamp(
      Number.isFinite(planningAltitudeM) ? planningAltitudeM : 25,
      10,
      120,
    );
    const position = CesiumModule.Cartesian3.fromDegrees(
      dc.lng,
      dc.lat,
      markerHeightM,
    );
    if (!droneEntityRef.current) {
      droneEntityRef.current = viewer.entities.add({
        position,
        billboard: {
          image: droneIconUrl,
          width: 40,
          height: 40,
          rotation: latestValuesRef.current.safeHeadingRad,
          alignedAxis: CesiumModule.Cartesian3.UNIT_Z,
          verticalOrigin: CesiumModule.VerticalOrigin.CENTER,
          horizontalOrigin: CesiumModule.HorizontalOrigin.CENTER,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: "DRONE",
          pixelOffset: new CesiumModule.Cartesian2(0, -22),
          scale: 0.85,
          showBackground: true,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      return;
    }

    droneEntityRef.current.position =
      new CesiumModule.ConstantPositionProperty(position);
    if (droneEntityRef.current.billboard) {
      droneEntityRef.current.billboard.rotation =
        new CesiumModule.ConstantProperty(latestValuesRef.current.safeHeadingRad);
    }
  }

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const CesiumModule = await import("cesium");
      if (cancelled) return;

      const token = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;
      if (token) CesiumModule.Ion.defaultAccessToken = token;

      CesiumRef.current = CesiumModule;

      if (!hostRef.current) return;

      const viewer = new CesiumModule.Viewer(hostRef.current, {
        animation: false,
        timeline: false,
        geocoder: false,
        baseLayerPicker: false,
        homeButton: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        infoBox: false,
        selectionIndicator: false,
        fullscreenButton: false,
        shouldAnimate: true,
      });

      viewer.scene.globe.depthTestAgainstTerrain = false;

      if (useWorldTerrain) {
        try {
          if (CesiumModule.createWorldTerrainAsync) {
            viewer.terrainProvider =
              await CesiumModule.createWorldTerrainAsync();
          } else if (
            typeof (CesiumModule as any).createWorldTerrain === "function"
          ) {
            viewer.terrainProvider = (CesiumModule as any).createWorldTerrain();
          }
        } catch {
          // keep default terrain
        }
      }

      if (cancelled) {
        try {
          viewer.destroy();
        } catch {}
        return;
      }

      viewerRef.current = viewer;

      const handler = new CesiumModule.ScreenSpaceEventHandler(
        viewer.scene.canvas,
      );
      handler.setInputAction((movement: any) => {
        if (drawModeRef.current !== "none") return;

        const picked = viewer.scene.pick(movement.position);
        if (
          picked?.id &&
          picked.id === fieldBoundaryEntityRef.current
        ) {
          onFieldBoundaryClickRef.current?.();
          return;
        }

        if (!onPickLatLngRef.current) return;
        const scene = viewer.scene;
        let cartesian: Cesium.Cartesian3 | null =
          scene.pickPosition?.(movement.position) ?? null;
        if (!cartesian) {
          cartesian =
            viewer.camera.pickEllipsoid(
              movement.position,
              scene.globe.ellipsoid,
            ) ?? null;
        }
        if (!cartesian) return;

        const carto = CesiumModule.Cartographic.fromCartesian(cartesian);
        const lat = CesiumModule.Math.toDegrees(carto.latitude);
        const lng = CesiumModule.Math.toDegrees(carto.longitude);
        if (Number.isFinite(lat) && Number.isFinite(lng)) {
          onPickLatLngRef.current({ lat, lng });
        }
      }, CesiumModule.ScreenSpaceEventType.LEFT_CLICK);
      clickHandlerRef.current = handler;

      const initialTarget = fieldCameraView?.center ?? droneCenter ?? center;
      const initialHeight =
        fieldCameraView?.topHeight ?? zoomToHeightMeters(zoom);
      viewer.camera.setView({
        destination: CesiumModule.Cartesian3.fromDegrees(
          initialTarget.lng,
          initialTarget.lat,
          initialHeight,
        ),
      });

      viewerReadyRef.current = true;
      drawEntities();
      updateDroneEntity();
      void loadFieldTileset(fieldTilesetUrlRef.current);
      applyCameraMode();
    })();

    return () => {
      cancelled = true;
      viewerReadyRef.current = false;

      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;

      try {
        clickHandlerRef.current?.destroy?.();
      } catch {}
      clickHandlerRef.current = null;

      tilesetLoadSeqRef.current += 1;
      const viewer = viewerRef.current;
      if (viewer && fieldTilesetRef.current) {
        try {
          viewer.scene.primitives.remove(fieldTilesetRef.current);
        } catch {
          // ignore cleanup errors
        }
      }
      fieldTilesetRef.current = null;

      try {
        viewer?.destroy?.();
      } catch {}
      viewerRef.current = null;
      CesiumRef.current = null;
    };
  }, [useWorldTerrain]);

  async function loadFieldTileset(url: string | null) {
    const CesiumModule = CesiumRef.current;
    const viewer = viewerRef.current;
    if (!CesiumModule || !viewer) return;

    const requestId = ++tilesetLoadSeqRef.current;

    if (fieldTilesetRef.current) {
      try {
        viewer.scene.primitives.remove(fieldTilesetRef.current);
      } catch {
        // ignore cleanup errors
      }
      fieldTilesetRef.current = null;
    }

    if (!url) return;

    let tilesetUrl = url.trim();
    if (!tilesetUrl) return;

    let tilesetUrlPointsToJson = /\.json(\?|$)/i.test(tilesetUrl);
    if (!tilesetUrlPointsToJson) {
      try {
        const parsed = new URL(tilesetUrl, window.location.origin);
        const signedAssetPath = parsed.searchParams.get("path")?.trim() ?? "";
        tilesetUrlPointsToJson =
          /\.json$/i.test(parsed.pathname) || /\.json$/i.test(signedAssetPath);
      } catch {
        tilesetUrlPointsToJson = false;
      }
    }
    if (!tilesetUrlPointsToJson) {
      tilesetUrl = `${tilesetUrl.replace(/\/$/, "")}/tileset.json`;
    }

    try {
      const tileset =
        typeof CesiumModule.Cesium3DTileset.fromUrl === "function"
          ? await CesiumModule.Cesium3DTileset.fromUrl(tilesetUrl, {
              maximumScreenSpaceError: 16,
            })
          : new (CesiumModule.Cesium3DTileset as any)({
              url: tilesetUrl,
              maximumScreenSpaceError: 16,
            });

      if (!viewerRef.current || requestId !== tilesetLoadSeqRef.current) {
        try {
          tileset.destroy();
        } catch {
          // ignore stale tileset cleanup errors
        }
        return;
      }

      viewer.scene.primitives.add(tileset);
      fieldTilesetRef.current = tileset;
    } catch (error) {
      console.error("Failed to load field 3D tileset", error);
    }
  }

  function drawEntities() {
    const CesiumModule = CesiumRef.current;
    const viewer = viewerRef.current;
    if (!CesiumModule || !viewer) return;

    if (polylineEntityRef.current)
      viewer.entities.remove(polylineEntityRef.current);
    if (waypointPolygonEntityRef.current)
      viewer.entities.remove(waypointPolygonEntityRef.current);
    if (plannedRouteEntityRef.current)
      viewer.entities.remove(plannedRouteEntityRef.current);
    if (fieldBoundaryEntityRef.current)
      viewer.entities.remove(fieldBoundaryEntityRef.current);
    exclusionZoneEntityRefs.current.forEach((e) => viewer.entities.remove(e));
    exclusionZoneEntityRefs.current = [];
    waypointEntityRefs.current.forEach((e) => viewer.entities.remove(e));
    waypointEntityRefs.current = [];

    const wp = waypoints
      .map((w) => ({ lat: w.lat, lng: w.lon }))
      .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng));

    const boundaryRing = normalizeLonLatRing(fieldBoundary);
    if (drawMode === "none" && boundaryRing.length >= 3) {
      const boundaryColor = drawnBoundarySelected ? "#1976d2" : "#1565c0";
      const boundaryPositions = CesiumModule.Cartesian3.fromDegreesArray(
        boundaryRing.flatMap(([lng, lat]) => [lng, lat]),
      );
      fieldBoundaryEntityRef.current = viewer.entities.add({
        polygon: {
          hierarchy: new CesiumModule.PolygonHierarchy(boundaryPositions),
          material: CesiumModule.Color.fromCssColorString(boundaryColor).withAlpha(
            drawnBoundarySelected ? 0.22 : 0.15,
          ),
          outline: true,
          outlineColor: CesiumModule.Color.fromCssColorString(boundaryColor),
          perPositionHeight: false,
        },
      });
    } else {
      fieldBoundaryEntityRef.current = null;
    }

    for (const zone of exclusionZones) {
      const ring = normalizeLonLatRing(zone);
      if (ring.length < 3) continue;
      const positions = CesiumModule.Cartesian3.fromDegreesArray(
        ring.flatMap(([lng, lat]) => [lng, lat]),
      );
      const entity = viewer.entities.add({
        polygon: {
          hierarchy: new CesiumModule.PolygonHierarchy(positions),
          material:
            CesiumModule.Color.fromCssColorString("#d32f2f").withAlpha(0.28),
          outline: true,
          outlineColor: CesiumModule.Color.fromCssColorString("#b71c1c"),
          perPositionHeight: false,
        },
      });
      exclusionZoneEntityRefs.current.push(entity);
    }

    const routeLine = normalizeLonLatLine(plannedRoute);
    if (routeLine.length >= 2) {
      const routePositions = CesiumModule.Cartesian3.fromDegreesArray(
        routeLine.flatMap(([lng, lat]) => [lng, lat]),
      );
      plannedRouteEntityRef.current = viewer.entities.add({
        polyline: {
          positions: routePositions,
          width: 4,
          material: CesiumModule.Color.fromCssColorString("#2e7d32"),
          clampToGround: true,
        },
      });
    } else {
      plannedRouteEntityRef.current = null;
    }

    wp.forEach((p) => {
      const ent = viewer.entities.add({
        position: CesiumModule.Cartesian3.fromDegrees(p.lng, p.lat),
        point: { pixelSize: 10 },
      });
      waypointEntityRefs.current.push(ent);
    });

    if (wp.length >= 2 && routeLine.length < 2) {
      const positions = wp.flatMap((p) => [p.lng, p.lat]);
      polylineEntityRef.current = viewer.entities.add({
        polyline: {
          positions: CesiumModule.Cartesian3.fromDegreesArray(positions),
          width: 3,
          clampToGround: true,
        },
      });
    } else {
      polylineEntityRef.current = null;
    }

    if (wp.length >= 3 && routeLine.length < 2) {
      const positions = CesiumModule.Cartesian3.fromDegreesArray(
        wp.flatMap((p) => [p.lng, p.lat]),
      );
      waypointPolygonEntityRef.current = viewer.entities.add({
        polygon: {
          hierarchy: new CesiumModule.PolygonHierarchy(positions),
          material:
            CesiumModule.Color.fromCssColorString("#1976d2").withAlpha(0.14),
          outline: true,
          outlineColor: CesiumModule.Color.fromCssColorString("#1976d2"),
          perPositionHeight: false,
        },
      });
    } else {
      waypointPolygonEntityRef.current = null;
    }

    updateDroneEntity();
  }

  useEffect(() => {
    drawEntities();
  }, [drawMode, waypoints, fieldBoundary, plannedRoute, exclusionZones, drawnBoundarySelected]);

  useEffect(() => {
    updateDroneEntity();
  }, [droneCenter, safeHeadingRad]);

  useEffect(() => {
    void loadFieldTileset(fieldTilesetUrl);
  }, [fieldTilesetUrl]);

  function pickCartesianOnGlobe(
    viewer: Cesium.Viewer,
    CesiumModule: typeof Cesium,
    screenPos: any,
  ) {
    const scene = viewer.scene;

    if (scene.pickPositionSupported && scene.pickPosition) {
      const picked = scene.pickPosition(screenPos);
      if (CesiumModule.defined(picked)) return picked;
    }

    const ray = viewer.camera.getPickRay(screenPos);
    if (!ray) return null;

    const picked = scene.globe.pick(ray, scene);
    return picked ?? null;
  }

  function cartesianToLngLat(
    CesiumModule: typeof Cesium,
    c: Cesium.Cartesian3,
  ): [number, number] {
    const carto = CesiumModule.Cartographic.fromCartesian(c);
    return [
      CesiumModule.Math.toDegrees(carto.longitude),
      CesiumModule.Math.toDegrees(carto.latitude),
    ];
  }

  function clearDrawEntities() {
    const viewer = viewerRef.current;
    if (!viewer) return;

    drawAnchorsRef.current.forEach((e) => viewer.entities.remove(e));
    drawAnchorsRef.current = [];

    if (drawTempEntityRef.current)
      viewer.entities.remove(drawTempEntityRef.current);
    drawTempEntityRef.current = null;

    if (drawFloatingPointRef.current)
      viewer.entities.remove(drawFloatingPointRef.current);
    drawFloatingPointRef.current = null;

    drawPositionsRef.current = [];
    drawFloatingCartesianRef.current = null;
    drawIsActiveRef.current = false;
    drawFreehandActiveRef.current = false;
  }

  function finishDraw(mode: DrawMode) {
    const CesiumModule = CesiumRef.current;
    const viewer = viewerRef.current;
    if (!CesiumModule || !viewer) return;

    const floating = drawFloatingCartesianRef.current;
    let coords: [number, number][];

    if (
      (mode === "rectangle" || mode === "circle" || mode === "triangle") &&
      drawPositionsRef.current.length >= 1
    ) {
      const anchor = drawPositionsRef.current[0];
      const corner = floating ?? drawPositionsRef.current[1];
      if (!anchor || !corner) return;
      coords = [
        cartesianToLngLat(CesiumModule, anchor),
        cartesianToLngLat(CesiumModule, corner),
      ];
    } else {
      let pos = drawPositionsRef.current.slice();
      if (floating) pos = pos.filter((p) => p !== floating);
      coords = pos.map((p) => cartesianToLngLat(CesiumModule, p));
    }

    const result = completeShape(mode, coords);
    if (result) onDrawCompleteRef.current?.(result);

    clearDrawEntities();
  }

  useEffect(() => {
    const CesiumModule = CesiumRef.current;
    const viewer = viewerRef.current;
    if (!CesiumModule || !viewer) return;

    try {
      drawHandlerRef.current?.destroy?.();
    } catch {}
    drawHandlerRef.current = null;

    clearDrawEntities();

    if (drawMode === "none") return;

    viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(
      CesiumModule.ScreenSpaceEventType.LEFT_DOUBLE_CLICK,
    );

    const handler = new CesiumModule.ScreenSpaceEventHandler(
      viewer.scene.canvas,
    );
    drawHandlerRef.current = handler;
    const canvas = viewer.scene.canvas;
    const preventContextMenu = (event: Event) => event.preventDefault();
    canvas.addEventListener("contextmenu", preventContextMenu);

    const ensureTempEntity = () => {
      if (drawTempEntityRef.current) return;

      const getPreviewCartesians = () => {
        const coords = drawPositionsRef.current.map((p) =>
          cartesianToLngLat(CesiumModule, p),
        );
        return shapePreview(drawMode, coords).map(([lng, lat]) =>
          CesiumModule.Cartesian3.fromDegrees(lng, lat),
        );
      };

      if (drawMode === "polyline") {
        drawTempEntityRef.current = viewer.entities.add({
          polyline: {
            positions: new CesiumModule.CallbackProperty(
              () => drawPositionsRef.current,
              false,
            ),
            width: 3,
            clampToGround: true,
          },
        });
      }

      if (
        ["polygon", "rectangle", "circle", "freehand", "triangle"].includes(
          drawMode,
        )
      ) {
        drawTempEntityRef.current = viewer.entities.add({
          polygon: {
            hierarchy: new CesiumModule.CallbackProperty(
              () => new CesiumModule.PolygonHierarchy(getPreviewCartesians()),
              false,
            ),
            material: CesiumModule.Color.YELLOW.withAlpha(0.25),
            outline: true,
            outlineColor: CesiumModule.Color.YELLOW,
          },
        });
      }
    };

    const addAnchor = (c: Cesium.Cartesian3) => {
      const ent = viewer.entities.add({
        position: c,
        point: {
          pixelSize: 10,
          color: CesiumModule.Color.YELLOW,
          outlineColor: CesiumModule.Color.BLACK,
          outlineWidth: 2,
        },
      });
      drawAnchorsRef.current.push(ent);
    };

    const committedDrawCoords = (): LonLat[] => {
      const floating = drawFloatingCartesianRef.current;
      let pos = drawPositionsRef.current.slice();
      if (floating) pos = pos.filter((p) => p !== floating);
      return pos.map((p) => cartesianToLngLat(CesiumModule, p));
    };

    const syncBoundaryDraw = (startedNew: boolean) => {
      if (!isFlatBoundaryDrawMode(drawMode)) return;
      if (startedNew) onBoundaryDrawStartedRef.current?.();
      const coords = committedDrawCoords();
      if (coords.length > 0) onBoundaryDrawProgressRef.current?.(coords);
    };

    handler.setInputAction((movement: any) => {
      const c = pickCartesianOnGlobe(viewer, CesiumModule, movement.position);
      if (!c) return;
      if (drawMode === "freehand") return;

      if (drawMode === "point") {
        addAnchor(c);
        onDrawCompleteRef.current?.({
          type: "point",
          coordinates: cartesianToLngLat(CesiumModule, c),
        });
        clearDrawEntities();
        return;
      }

      ensureTempEntity();

      if (
        drawMode === "rectangle" ||
        drawMode === "circle" ||
        drawMode === "triangle"
      ) {
        if (!drawIsActiveRef.current) {
          drawIsActiveRef.current = true;
          drawPositionsRef.current = [c, c.clone()];
          addAnchor(c);
          const floating = drawPositionsRef.current[1];
          drawFloatingCartesianRef.current = floating;
          drawFloatingPointRef.current = viewer.entities.add({
            position: floating,
            point: { pixelSize: 8, color: CesiumModule.Color.YELLOW },
          });
          syncBoundaryDraw(true);
          return;
        }
        const floating = drawFloatingCartesianRef.current;
        if (floating) {
          floating.x = c.x;
          floating.y = c.y;
          floating.z = c.z;
        }
        finishDraw(drawMode);
        return;
      }

      if (!drawIsActiveRef.current) {
        drawIsActiveRef.current = true;

        drawPositionsRef.current.push(c);
        addAnchor(c);

        const floating = c.clone();
        drawFloatingCartesianRef.current = floating;
        drawPositionsRef.current.push(floating);

        drawFloatingPointRef.current = viewer.entities.add({
          position: floating,
          point: { pixelSize: 8, color: CesiumModule.Color.YELLOW },
        });
        syncBoundaryDraw(true);
        return;
      }

      const floating = drawFloatingCartesianRef.current;
      if (floating) {
        drawPositionsRef.current = drawPositionsRef.current.filter(
          (p) => p !== floating,
        );
      }

      const committed = drawPositionsRef.current.map((p) =>
        cartesianToLngLat(CesiumModule, p),
      );
      const clickCoord = cartesianToLngLat(CesiumModule, c);
      if (
        (drawMode === "polygon" || drawMode === "polyline") &&
        committed.length >= 3 &&
        isNearLonLat(committed[0], clickCoord)
      ) {
        finishDraw(drawMode);
        return;
      }

      drawPositionsRef.current.push(c);
      addAnchor(c);

      const newFloating = c.clone();
      drawFloatingCartesianRef.current = newFloating;
      drawPositionsRef.current.push(newFloating);

      if (drawFloatingPointRef.current) {
        drawFloatingPointRef.current.position =
          new CesiumModule.ConstantPositionProperty(newFloating);
      }
      syncBoundaryDraw(false);
    }, CesiumModule.ScreenSpaceEventType.LEFT_CLICK);

    handler.setInputAction((movement: any) => {
      if (drawMode !== "freehand") return;
      const c = pickCartesianOnGlobe(viewer, CesiumModule, movement.position);
      if (!c) return;
      clearDrawEntities();
      drawFreehandActiveRef.current = true;
      drawIsActiveRef.current = true;
      drawPositionsRef.current = [c];
      ensureTempEntity();
      syncBoundaryDraw(true);
    }, CesiumModule.ScreenSpaceEventType.LEFT_DOWN);

    handler.setInputAction((movement: any) => {
      if (!drawIsActiveRef.current) return;

      if (drawMode !== "freehand") {
        const floating = drawFloatingCartesianRef.current;
        if (!floating) return;

        const c = pickCartesianOnGlobe(
          viewer,
          CesiumModule,
          movement.endPosition,
        );
        if (!c) return;

        floating.x = c.x;
        floating.y = c.y;
        floating.z = c.z;
        return;
      }

      if (!drawFreehandActiveRef.current) return;
      const c = pickCartesianOnGlobe(
        viewer,
        CesiumModule,
        movement.endPosition,
      );
      if (!c) return;
      const last =
        drawPositionsRef.current[drawPositionsRef.current.length - 1];
      if (last && CesiumModule.Cartesian3.distance(last, c) < 0.5) return;
      drawPositionsRef.current.push(c);
    }, CesiumModule.ScreenSpaceEventType.MOUSE_MOVE);

    handler.setInputAction(() => {
      if (drawMode !== "freehand" || !drawFreehandActiveRef.current) return;
      finishDraw(drawMode);
    }, CesiumModule.ScreenSpaceEventType.LEFT_UP);

    handler.setInputAction(() => {
      finishDraw(drawMode);
    }, CesiumModule.ScreenSpaceEventType.RIGHT_CLICK);
    handler.setInputAction(() => {
      finishDraw(drawMode);
    }, CesiumModule.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") clearDrawEntities();
      if (e.key === "Enter") finishDraw(drawMode);
    };
    window.addEventListener("keydown", onKey);

    return () => {
      window.removeEventListener("keydown", onKey);
      canvas.removeEventListener("contextmenu", preventContextMenu);
      try {
        handler.destroy();
      } catch {}
      drawHandlerRef.current = null;
      clearDrawEntities();
    };
  }, [drawMode]);

  function applyCameraMode() {
    const CesiumModule = CesiumRef.current;
    const viewer = viewerRef.current;
    if (!CesiumModule || !viewer) return;

    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;

    viewer.trackedEntity = undefined;

    const {
      droneCenter: dc,
      center: c,
      safeHeadingRad: headingRad,
      fieldCameraView: fieldView,
    } = latestValuesRef.current;
    const planningHeight = clamp(
      Number.isFinite(planningAltitudeM) ? planningAltitudeM : 25,
      20,
      30,
    );
    const defaultBaseHeight = lockCameraToPlanningAltitude
      ? planningHeight
      : zoomToHeightMeters(zoom);
    const baseHeight =
      !lockCameraToPlanningAltitude && !dc && fieldView
        ? fieldView.topHeight
        : defaultBaseHeight;
    const tiltedHeight = lockCameraToPlanningAltitude
      ? clamp(baseHeight + 5, 20, 30)
      : Math.max(500, Math.round(baseHeight * 0.6));
    const followHeight = lockCameraToPlanningAltitude
      ? clamp(baseHeight + 4, 20, 30)
      : Math.max(300, Math.round(baseHeight * 0.4));
    const overviewTarget = fieldView?.center ?? c;
    const target =
      viewMode === "follow" || viewMode === "fpv" || viewMode === "orbit"
        ? dc ?? overviewTarget
        : overviewTarget;

    const setView = (opts: {
      lat: number;
      lng: number;
      height: number;
      headingRad?: number;
      pitchRad?: number;
      rollRad?: number;
      fly?: boolean;
      signature?: string;
    }) => {
      if (opts.signature && lastCameraSignatureRef.current === opts.signature) {
        return;
      }
      if (opts.signature) {
        lastCameraSignatureRef.current = opts.signature;
      }
      const destination = CesiumModule.Cartesian3.fromDegrees(
        opts.lng,
        opts.lat,
        opts.height,
      );
      const orientation = {
        heading: opts.headingRad ?? 0,
        pitch: opts.pitchRad ?? CesiumModule.Math.toRadians(-60),
        roll: opts.rollRad ?? 0,
      };
      if (opts.fly) {
        viewer.camera.flyTo({ destination, orientation, duration: 0.6 });
      } else {
        viewer.camera.setView({ destination, orientation });
      }
    };

    if (viewMode === "top") {
      const signature = [
        viewMode,
        target.lat.toFixed(7),
        target.lng.toFixed(7),
        Math.round(baseHeight),
        fieldView ? "field" : "center",
      ].join(":");
      setView({
        lat: target.lat,
        lng: target.lng,
        height: baseHeight,
        headingRad: 0,
        pitchRad: CesiumModule.Math.toRadians(-90),
        fly: true,
        signature,
      });
      return;
    }

    if (viewMode === "tilted") {
      const signature = [
        viewMode,
        target.lat.toFixed(7),
        target.lng.toFixed(7),
        Math.round(tiltedHeight),
        fieldView ? "field" : "center",
      ].join(":");
      setView({
        lat: target.lat,
        lng: target.lng,
        height: tiltedHeight,
        headingRad: 0,
        pitchRad: CesiumModule.Math.toRadians(-45),
        fly: true,
        signature,
      });
      return;
    }

    if (viewMode === "follow") {
      lastCameraSignatureRef.current = null;
      if (droneEntityRef.current) {
        viewer.trackedEntity = droneEntityRef.current;
        setView({
          lat: target.lat,
          lng: target.lng,
          height: followHeight,
          headingRad: headingRad,
          pitchRad: CesiumModule.Math.toRadians(-35),
          fly: true,
        });
      } else {
        setView({
          lat: c.lat,
          lng: c.lng,
          height: tiltedHeight,
          headingRad: 0,
          pitchRad: CesiumModule.Math.toRadians(-45),
          fly: true,
        });
      }
      return;
    }

    const getCurrentCameraHeight = (): number => {
      if (lockCameraToPlanningAltitude) return baseHeight;
      try {
        const camCarto = CesiumModule.Cartographic.fromCartesian(
          viewer.camera.position,
        );
        const h = camCarto.height;
        return Number.isFinite(h) && h > 0 ? h : baseHeight;
      } catch {
        return baseHeight;
      }
    };

    const tickFPV = () => {
      if (!userInteractingRef.current) {
        const {
          droneCenter: p0,
          center: p1,
          safeHeadingRad: hr,
          fieldCameraView: fv,
        } = latestValuesRef.current;
        const p = p0 ?? fv?.center ?? p1;

        const currentHeight = lockCameraToPlanningAltitude
          ? baseHeight
          : Math.max(5, getCurrentCameraHeight());
        const currentPitch = viewer.camera.pitch;

        setView({
          lat: p.lat,
          lng: p.lng,
          height: currentHeight,
          headingRad: hr,
          pitchRad: currentPitch,
          rollRad: 0,
          fly: false,
        });
      }
      rafRef.current = requestAnimationFrame(tickFPV);
    };

    const tickOrbit = () => {
      if (!userInteractingRef.current) {
        const {
          droneCenter: p0,
          center: p1,
          fieldCameraView: fv,
        } = latestValuesRef.current;
        const p = p0 ?? fv?.center ?? p1;
        const t = performance.now() * 0.00015;
        const radiusMeters = lockCameraToPlanningAltitude ? 35 : 250;

        const heightMeters = lockCameraToPlanningAltitude
          ? baseHeight
          : Math.max(50, getCurrentCameraHeight());

        const dLat = (radiusMeters * Math.cos(t)) / 111_320;
        const dLng =
          (radiusMeters * Math.sin(t)) /
          (111_320 * Math.cos((p.lat * Math.PI) / 180));
        const camLat = p.lat + dLat;
        const camLng = p.lng + dLng;
        const heading = Math.atan2(p.lng - camLng, p.lat - camLat);
        setView({
          lat: camLat,
          lng: camLng,
          height: heightMeters,
          headingRad: heading,
          pitchRad: CesiumModule.Math.toRadians(-25),
          rollRad: 0,
          fly: false,
        });
      }
      rafRef.current = requestAnimationFrame(tickOrbit);
    };

    if (viewMode === "fpv") {
      lastCameraSignatureRef.current = null;
      tickFPV();
      return;
    }
    if (viewMode === "orbit") {
      lastCameraSignatureRef.current = null;
      tickOrbit();
      return;
    }
  }

  useEffect(() => {
    applyCameraMode();
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [
    viewMode,
    cameraCenterKey,
    zoom,
    hasDroneCenter,
    fieldCameraView?.center.lat,
    fieldCameraView?.center.lng,
    fieldCameraView?.topHeight,
    planningAltitudeM,
    lockCameraToPlanningAltitude,
    focusRequestToken,
  ]);

  useEffect(() => {
    if (focusRequestToken == null) return;
    const ring = focusRing ?? fieldBoundary;
    if (!ring || ring.length < 3) return;
    const viewer = viewerRef.current;
    const CesiumModule = CesiumRef.current;
    if (!viewer || !CesiumModule) return;

    const fieldView = computeFieldCameraView(ring);
    if (!fieldView) return;

    lastCameraSignatureRef.current = null;
    viewer.trackedEntity = undefined;
    const pitch =
      viewMode === "top"
        ? CesiumModule.Math.toRadians(-90)
        : CesiumModule.Math.toRadians(-45);
    viewer.camera.flyTo({
      destination: CesiumModule.Cartesian3.fromDegrees(
        fieldView.center.lng,
        fieldView.center.lat,
        fieldView.topHeight,
      ),
      orientation: {
        heading: 0,
        pitch,
        roll: 0,
      },
      duration: 0.6,
    });
  }, [fieldBoundary, focusRequestToken, focusRing, viewMode]);

  return (
    <div
      ref={hostRef}
      style={{
        width: "100%",
        height: 400,
        borderRadius: 12,
        overflow: "hidden",
      }}
    />
  );
}
