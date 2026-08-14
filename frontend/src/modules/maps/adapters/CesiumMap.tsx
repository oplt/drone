import "cesium/Build/Cesium/Widgets/widgets.css";
import {
  EMPTY_EXCLUSION_ZONES,
  type CesiumMapProps,
  type CesiumViewMode,
  type DrawMode,
  type DrawResult,
} from "./cesium/cesiumMapTypes";
import { useCesiumMapSession } from "../hooks/useCesiumMapSession";

export type { CesiumViewMode, DrawMode, DrawResult };

export default function CesiumMap(props: CesiumMapProps) {
  const hostRef = useCesiumMapSession({
    ...props,
    exclusionZones: props.exclusionZones ?? EMPTY_EXCLUSION_ZONES,
  });

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
