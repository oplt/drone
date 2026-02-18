import { useEffect, useMemo, useRef } from "react";
import "cesium/Build/Cesium/Widgets/widgets.css";

type LatLng = { lat: number; lng: number };
type Waypoint = { lat: number; lon: number; alt: number };

export type CesiumViewMode = "top" | "tilted" | "follow" | "fpv" | "orbit";

type Props = {
  center: LatLng;
  zoom: number;
  viewMode: CesiumViewMode;

  waypoints: Waypoint[];
  droneCenter: LatLng | null;
  headingDeg?: number | null;

  onPickLatLng?: (p: LatLng) => void;
};

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

// Rough mapping from "web zoom" to camera height.
function zoomToHeightMeters(zoom: number) {
  const z = clamp(zoom, 1, 20);
  return Math.round(20000000 / Math.pow(2, z));
}

export default function CesiumMap({
  center,
  zoom,
  viewMode,
  waypoints,
  droneCenter,
  headingDeg,
  onPickLatLng,
}: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  const CesiumRef = useRef<any>(null);
  const viewerRef = useRef<any>(null);
  const clickHandlerRef = useRef<any>(null);

  const rafRef = useRef<number | null>(null);

  const droneEntityRef = useRef<any>(null);
  const polylineEntityRef = useRef<any>(null);
  const waypointEntityRefs = useRef<any[]>([]);

  // Keep a stable ref to the callback so the click handler never goes stale.
  const onPickLatLngRef = useRef<Props["onPickLatLng"]>(onPickLatLng);
  useEffect(() => {
    onPickLatLngRef.current = onPickLatLng;
  }, [onPickLatLng]);

  const safeHeadingRad = useMemo(() => {
    const h = typeof headingDeg === "number" && Number.isFinite(headingDeg) ? headingDeg : 0;
    return (h * Math.PI) / 180;
  }, [headingDeg]);

  // Stable ref so RAF tick functions can read latest values without being
  // included in effect deps (which would restart the RAF loop on every update).
  const latestValuesRef = useRef({ droneCenter, center, safeHeadingRad });

  // Tracks whether the user is actively interacting with the map (mouse/touch
  // down). While true, orbit/fpv tick functions skip their setView call so the
  // user can freely pan/zoom/rotate, then camera control resumes automatically.
  const userInteractingRef = useRef(false);
  const interactionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    latestValuesRef.current = { droneCenter, center, safeHeadingRad };
  });

  // Track user interaction so RAF tick functions can pause their setView calls.
  //
  // Key design decisions:
  //   - mousedown/touchstart on the canvas starts interaction
  //   - mousemove/touchmove on the *document* keeps it alive during drags
  //     (the pointer often leaves the canvas element mid-drag)
  //   - mouseup/touchend on the *document* ends it, with a short debounce so
  //     the camera doesn't snap back before the user has fully released
  //   - wheel on the canvas is self-contained (no move phase)
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

    // Keep the flag alive while the pointer is moving (covers the whole drag).
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

    // Canvas-level: start
    el.addEventListener("mousedown", startInteraction);
    el.addEventListener("touchstart", startInteraction, { passive: true });
    el.addEventListener("wheel", startInteraction, { passive: true });

    // Document-level: keep alive during drag & end on release.
    // Using document ensures we catch events even when the cursor leaves the canvas.
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

  // --- viewer ready signal ---
  // We use a counter ref + a forceUpdate-style trick so other effects can
  // re-run once the async viewer is initialised.  A simple boolean ref won't
  // trigger re-renders / effect re-runs, so we use a separate state-like ref
  // together with explicit imperative calls after init.
  const viewerReadyRef = useRef(false);

  // --- Create / destroy viewer ---
  useEffect(() => {
    let cancelled = false;

    (async () => {
      const Cesium = await import("cesium");
      if (cancelled) return;

      const token = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;
      if (token) Cesium.Ion.defaultAccessToken = token;

      CesiumRef.current = Cesium;

      if (!hostRef.current) return;

      const viewer = new Cesium.Viewer(hostRef.current, {
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

      viewer.scene.globe.depthTestAgainstTerrain = true;

      try {
        if (Cesium.createWorldTerrainAsync) {
          viewer.terrainProvider = await Cesium.createWorldTerrainAsync();
        } else if (Cesium.createWorldTerrain) {
          viewer.terrainProvider = Cesium.createWorldTerrain();
        }
      } catch {
        // keep default terrain
      }

      if (cancelled) {
        try { viewer.destroy(); } catch {}
        return;
      }

      viewerRef.current = viewer;

      // FIX #1: Always register the click handler, calling through the ref.
      // This way it works even if onPickLatLng is initially undefined and
      // later provided, and never needs re-registration.
      const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
      handler.setInputAction((movement: any) => {
        if (!onPickLatLngRef.current) return;
        const scene = viewer.scene;
        let cartesian = scene.pickPosition?.(movement.position);
        if (!cartesian) {
          cartesian = viewer.camera.pickEllipsoid(movement.position, scene.globe.ellipsoid);
        }
        if (!cartesian) return;

        const carto = Cesium.Cartographic.fromCartesian(cartesian);
        const lat = Cesium.Math.toDegrees(carto.latitude);
        const lng = Cesium.Math.toDegrees(carto.longitude);
        if (Number.isFinite(lat) && Number.isFinite(lng)) {
          onPickLatLngRef.current({ lat, lng });
        }
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
      clickHandlerRef.current = handler;

      // FIX #5: Apply initial camera position from current props.
      const height = zoomToHeightMeters(zoom);
      viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(center.lng, center.lat, height),
      });

      // FIX #2 & #3: Viewer is now ready — imperatively draw entities and
      // apply the camera mode so the dependent effects don't silently no-op
      // during the async init window.
      viewerReadyRef.current = true;
      drawEntities();
      applyCameraMode();
    })();

    return () => {
      cancelled = true;
      viewerReadyRef.current = false;

      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;

      try { clickHandlerRef.current?.destroy?.(); } catch {}
      clickHandlerRef.current = null;

      try { viewerRef.current?.destroy?.(); } catch {}
      viewerRef.current = null;
      CesiumRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Draw/update entities (extracted so it can be called imperatively) ---
  function drawEntities() {
    const Cesium = CesiumRef.current;
    const viewer = viewerRef.current;
    if (!Cesium || !viewer) return;

    if (droneEntityRef.current) viewer.entities.remove(droneEntityRef.current);
    if (polylineEntityRef.current) viewer.entities.remove(polylineEntityRef.current);
    waypointEntityRefs.current.forEach((e) => viewer.entities.remove(e));
    waypointEntityRefs.current = [];

    const wp = waypoints
      .map((w) => ({ lat: w.lat, lng: w.lon }))
      .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng));

    wp.forEach((p, idx) => {
      const ent = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(p.lng, p.lat),
        point: { pixelSize: 10 },
        label: {
          text: String(idx + 1),
          pixelOffset: new Cesium.Cartesian2(0, -18),
          scale: 0.9,
          showBackground: true,
        },
      });
      waypointEntityRefs.current.push(ent);
    });

    if (wp.length >= 2) {
      const positions = wp.flatMap((p) => [p.lng, p.lat]);
      polylineEntityRef.current = viewer.entities.add({
        polyline: {
          positions: Cesium.Cartesian3.fromDegreesArray(positions),
          width: 3,
          clampToGround: true,
        },
      });
    } else {
      polylineEntityRef.current = null;
    }

    const dc = latestValuesRef.current.droneCenter;
    if (dc) {
      droneEntityRef.current = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(dc.lng, dc.lat),
        point: { pixelSize: 14 },
        label: {
          text: "DRONE",
          pixelOffset: new Cesium.Cartesian2(0, -22),
          scale: 0.85,
          showBackground: true,
        },
      });
    } else {
      droneEntityRef.current = null;
    }
  }

  // FIX #2: Re-run entity drawing when data changes; guard with viewerReadyRef
  // so this is a no-op if the viewer isn't ready yet (drawEntities() will be
  // called imperatively once init completes).
  useEffect(() => {
    if (!viewerReadyRef.current) return;
    drawEntities();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waypoints, droneCenter]);

  // --- Camera controller ---
  function applyCameraMode() {
    const Cesium = CesiumRef.current;
    const viewer = viewerRef.current;
    if (!Cesium || !viewer) return;

    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;

    viewer.trackedEntity = undefined;

    const { droneCenter: dc, center: c, safeHeadingRad: headingRad } = latestValuesRef.current;
    const baseHeight = zoomToHeightMeters(zoom);
    const target = dc ?? c;

    const setView = (opts: {
      lat: number;
      lng: number;
      height: number;
      headingRad?: number;
      pitchRad?: number;
      rollRad?: number;
      fly?: boolean;
    }) => {
      const destination = Cesium.Cartesian3.fromDegrees(opts.lng, opts.lat, opts.height);
      const orientation = {
        heading: opts.headingRad ?? 0,
        pitch: opts.pitchRad ?? Cesium.Math.toRadians(-60),
        roll: opts.rollRad ?? 0,
      };
      if (opts.fly) {
        viewer.camera.flyTo({ destination, orientation, duration: 0.6 });
      } else {
        viewer.camera.setView({ destination, orientation });
      }
    };

    if (viewMode === "top") {
      setView({
        lat: target.lat, lng: target.lng, height: baseHeight,
        headingRad: 0, pitchRad: Cesium.Math.toRadians(-90), fly: true,
      });
      return;
    }

    if (viewMode === "tilted") {
      setView({
        lat: target.lat, lng: target.lng,
        height: Math.max(500, Math.round(baseHeight * 0.6)),
        headingRad: 0, pitchRad: Cesium.Math.toRadians(-45), fly: true,
      });
      return;
    }

    if (viewMode === "follow") {
      // FIX #4: Read droneEntityRef.current at call time (after drawEntities
      // has run), not at effect-setup time, so it's never stale.
      if (droneEntityRef.current) {
        viewer.trackedEntity = droneEntityRef.current;
        setView({
          lat: target.lat, lng: target.lng,
          height: Math.max(300, Math.round(baseHeight * 0.4)),
          headingRad: headingRad, pitchRad: Cesium.Math.toRadians(-35), fly: true,
        });
      } else {
        setView({
          lat: c.lat, lng: c.lng,
          height: Math.max(500, Math.round(baseHeight * 0.6)),
          headingRad: 0, pitchRad: Cesium.Math.toRadians(-45), fly: true,
        });
      }
      return;
    }

    // Helper: read the current camera height above the ellipsoid in metres.
    // Falls back to the initial baseHeight if the position is unavailable.
    const getCurrentCameraHeight = (): number => {
      try {
        const camCarto = Cesium.Cartographic.fromCartesian(viewer.camera.position);
        const h = camCarto.height;
        return Number.isFinite(h) && h > 0 ? h : baseHeight;
      } catch {
        return baseHeight;
      }
    };

    const tickFPV = () => {
      // While the user is actively interacting, do nothing — Cesium's own input
      // handler has full control.  The loop keeps running so it resumes the
      // moment interaction ends without any perceptible gap.
      if (!userInteractingRef.current) {
        const { droneCenter: p0, center: p1, safeHeadingRad: hr } = latestValuesRef.current;
        const p = p0 ?? p1;

        // KEY FIX: preserve whatever height the user has scrolled to instead of
        // snapping back to a hard-coded 25 m.  Clamp to a sensible minimum so
        // the camera doesn't go underground.
        const currentHeight = Math.max(5, getCurrentCameraHeight());

        // Preserve the current pitch too so a user tilt isn't reset each frame.
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
      // While interacting, skip the override entirely.
      if (!userInteractingRef.current) {
        const { droneCenter: p0, center: p1 } = latestValuesRef.current;
        const p = p0 ?? p1;
        const t = performance.now() * 0.00015;
        const radiusMeters = 250;

        // Preserve the user's zoom level the same way as FPV: read back the
        // current height instead of locking to a fixed value.
        const heightMeters = Math.max(50, getCurrentCameraHeight());

        const dLat = (radiusMeters * Math.cos(t)) / 111_320;
        const dLng = (radiusMeters * Math.sin(t)) / (111_320 * Math.cos((p.lat * Math.PI) / 180));
        const camLat = p.lat + dLat;
        const camLng = p.lng + dLng;
        const heading = Math.atan2(p.lng - camLng, p.lat - camLat);
        setView({
          lat: camLat, lng: camLng, height: heightMeters,
          headingRad: heading, pitchRad: Cesium.Math.toRadians(-25), rollRad: 0, fly: false,
        });
      }
      rafRef.current = requestAnimationFrame(tickOrbit);
    };

    if (viewMode === "fpv") { tickFPV(); return; }
    if (viewMode === "orbit") { tickOrbit(); return; }
  }

  // FIX #3 & #6: Re-apply camera mode when relevant props change; guard with
  // viewerReadyRef; return a cleanup that cancels any running RAF loop.
  useEffect(() => {
    if (!viewerReadyRef.current) return;
    applyCameraMode();
    return () => {
      // FIX #6: always cancel RAF on cleanup (mode change or unmount)
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, center.lat, center.lng, zoom, droneCenter?.lat, droneCenter?.lng, safeHeadingRad]);

  return (
    <div
      ref={hostRef}
      style={{ width: "100%", height: 400, borderRadius: 12, overflow: "hidden" }}
    />
  );
}