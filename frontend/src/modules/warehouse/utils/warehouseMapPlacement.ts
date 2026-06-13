import type {
  WarehouseLocalPose,
  WarehouseScanTarget,
  WarehouseShelfNormal,
} from "../api/warehouseInspectionApi";

export type MapPlacementPoint = {
  x_m: number;
  y_m: number;
  z_m: number;
};

export const WAREHOUSE_MAP_FRAME_ID = "warehouse_map";

export const SHELF_FACE_OPTIONS: Array<{
  id: string;
  label: string;
  normal: WarehouseShelfNormal;
}> = [
  { id: "+y", label: "Faces +Y (aisle along X)", normal: { x: 0, y: 1, z: 0 } },
  { id: "-y", label: "Faces -Y", normal: { x: 0, y: -1, z: 0 } },
  { id: "+x", label: "Faces +X", normal: { x: 1, y: 0, z: 0 } },
  { id: "-x", label: "Faces -X", normal: { x: -1, y: 0, z: 0 } },
];

export function formatMapPoint(point: MapPlacementPoint): string {
  return `${point.x_m.toFixed(2)}, ${point.y_m.toFixed(2)}, ${point.z_m.toFixed(2)}`;
}

export function shelfNormalFromFacing(facingId: string): WarehouseShelfNormal {
  return (
    SHELF_FACE_OPTIONS.find((option) => option.id === facingId)?.normal ?? {
      x: 0,
      y: 1,
      z: 0,
    }
  );
}

export function scanTargetsForMapMarkers(
  targets: WarehouseScanTarget[],
): Array<{
  id: number;
  label: string;
  target: MapPlacementPoint;
  scanPose: WarehouseLocalPose;
}> {
  return targets.map((target) => ({
    id: target.id,
    label: [target.aisle_code, target.rack_code, target.bin_code]
      .filter(Boolean)
      .join(" / "),
    target: {
      x_m: target.target_point_local_json.x_m,
      y_m: target.target_point_local_json.y_m,
      z_m: target.target_point_local_json.z_m,
    },
    scanPose: target.scan_pose_local_json,
  }));
}
