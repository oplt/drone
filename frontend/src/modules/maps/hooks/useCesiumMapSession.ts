import { useEffect, useMemo } from "react";
import { computeFieldCameraView } from "../utils/cesiumCameraGeometry";
import type { CesiumMapProps } from "../adapters/cesium/cesiumMapTypes";
import { useCesiumDrawSession } from "./useCesiumDrawSession";
import { useCesiumMapRefs } from "./useCesiumMapRefs";
import { useCesiumSceneLayers } from "./useCesiumSceneLayers";
import { useCesiumUserInteraction } from "./useCesiumUserInteraction";
import { useCesiumViewerLifecycle } from "./useCesiumViewerLifecycle";
import { useCesiumViewCamera } from "./useCesiumViewCamera";

export function useCesiumMapSession(props: CesiumMapProps) {
  const refs = useCesiumMapRefs(props);
  const drawMode = props.drawMode ?? "none";

  const safeHeadingRad = useMemo(() => {
    const heading =
      typeof props.headingDeg === "number" && Number.isFinite(props.headingDeg)
        ? props.headingDeg
        : 0;
    return (heading * Math.PI) / 180;
  }, [props.headingDeg]);

  const fieldCameraView = useMemo(
    () => (drawMode !== "none" ? null : computeFieldCameraView(props.fieldBoundary ?? null)),
    [props.fieldBoundary, drawMode],
  );

  const hasDroneCenter = Boolean(props.droneCenter);
  const cameraCenterKey = hasDroneCenter
    ? `drone-live:${fieldCameraView?.center.lat.toFixed(7) ?? "none"}:${fieldCameraView?.center.lng.toFixed(7) ?? "none"}:${props.focusRequestToken ?? 0}`
    : `${props.center.lat.toFixed(7)}:${props.center.lng.toFixed(7)}:${props.focusRequestToken ?? 0}`;

  useEffect(() => {
    refs.latestValuesRef.current = {
      droneCenter: props.droneCenter,
      center: props.center,
      safeHeadingRad,
      fieldCameraView,
    };
  }, [props.droneCenter, props.center, safeHeadingRad, fieldCameraView, refs]);

  useCesiumUserInteraction(refs);
  useCesiumViewerLifecycle({ refs, props, fieldCameraView });
  useCesiumSceneLayers({ refs, props, safeHeadingRad });
  useCesiumDrawSession(refs, drawMode);
  useCesiumViewCamera({
    refs,
    props,
    cameraCenterKey,
    hasDroneCenter,
    fieldCameraView,
  });

  return refs.hostRef;
}
