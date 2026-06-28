import * as THREE from "three";
import type { WarehouseCoordinateFrame } from "../api/warehouseInspectionApi";
import type { MapPlacementPoint } from "./warehouseMapPlacement";

export const WAREHOUSE_MAP_FRAME = "warehouse_map";

export type WarehouseSceneTransform = {
  displayFrameId: string;
  coordinateFrameId: number;
  coordinateFrameVersion: number;
  warehouseToScene: THREE.Matrix4;
  sceneToWarehouse: THREE.Matrix4;
};

function matrixFromCoordinateFrame(frame: WarehouseCoordinateFrame): THREE.Matrix4 {
  const { translation, rotation } = frame.transform;
  return new THREE.Matrix4().compose(
    new THREE.Vector3(translation.x, translation.y, translation.z),
    new THREE.Quaternion(rotation.x, rotation.y, rotation.z, rotation.w),
    new THREE.Vector3(1, 1, 1),
  );
}

export function createWarehouseSceneTransform(
  displayFrameId: string,
  frame: WarehouseCoordinateFrame,
): WarehouseSceneTransform | null {
  if (frame.parent_frame_id !== WAREHOUSE_MAP_FRAME) return null;
  const odomToWarehouse = matrixFromCoordinateFrame(frame);
  let sceneToWarehouse: THREE.Matrix4;
  if (displayFrameId === WAREHOUSE_MAP_FRAME) {
    sceneToWarehouse = new THREE.Matrix4();
  } else if (displayFrameId === frame.child_frame_id) {
    sceneToWarehouse = odomToWarehouse;
  } else {
    return null;
  }
  return {
    displayFrameId,
    coordinateFrameId: frame.id,
    coordinateFrameVersion: frame.version,
    sceneToWarehouse,
    warehouseToScene: sceneToWarehouse.clone().invert(),
  };
}

function transformPoint(point: MapPlacementPoint, matrix: THREE.Matrix4): MapPlacementPoint {
  const transformed = new THREE.Vector3(point.x_m, point.y_m, point.z_m).applyMatrix4(matrix);
  return { x_m: transformed.x, y_m: transformed.y, z_m: transformed.z };
}

export function sceneToWarehouseMap(
  point: MapPlacementPoint,
  transform: WarehouseSceneTransform,
): MapPlacementPoint {
  return transformPoint(point, transform.sceneToWarehouse);
}

export function warehouseMapToScene(
  point: MapPlacementPoint,
  transform: WarehouseSceneTransform,
): MapPlacementPoint {
  return transformPoint(point, transform.warehouseToScene);
}

export function resolveDisplayedFrame(frameIds: Array<string | null | undefined>): string | null {
  const frames = new Set(frameIds.map((value) => value?.trim()).filter(Boolean));
  return frames.size === 1 ? ([...frames][0] as string) : null;
}
