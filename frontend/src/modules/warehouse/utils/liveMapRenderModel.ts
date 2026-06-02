import type {
  WarehouseLivePose,
  WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";

export type LiveMapRenderChunk = {
  id: string;
  kind: WarehouseLiveVoxelChunk["kind"];
  sequence: number;
  center: [number, number, number];
  size: [number, number, number];
  pointCount: number;
  hasGeometry: boolean;
};

function centerFromBbox(bbox: number[]): [number, number, number] {
  return [
    (bbox[0] + bbox[3]) / 2,
    (bbox[1] + bbox[4]) / 2,
    (bbox[2] + bbox[5]) / 2,
  ];
}

function sizeFromBbox(bbox: number[]): [number, number, number] {
  return [
    Math.max(0.08, bbox[3] - bbox[0]),
    Math.max(0.08, bbox[4] - bbox[1]),
    Math.max(0.08, bbox[5] - bbox[2]),
  ];
}

export function toRenderChunks(
  chunks: WarehouseLiveVoxelChunk[],
): LiveMapRenderChunk[] {
  return chunks.slice(-180).map((chunk, index) => {
    const bbox =
      Array.isArray(chunk.bbox_local_m) && chunk.bbox_local_m.length === 6
        ? chunk.bbox_local_m
        : null;
    const ring = 1 + Math.floor(index / 20);
    const angle = index * 0.91;
    const fallbackCenter: [number, number, number] = [
      Math.cos(angle) * ring,
      Math.sin(angle) * ring,
      chunk.kind === "point_cloud" ? 0.35 : 0.6,
    ];
    return {
      id: chunk.id,
      kind: chunk.kind,
      sequence: chunk.sequence ?? index,
      center: bbox ? centerFromBbox(bbox) : fallbackCenter,
      size: bbox ? sizeFromBbox(bbox) : [0.28, 0.28, 0.28],
      pointCount: chunk.point_count ?? 0,
      hasGeometry: Boolean(chunk.url),
    };
  });
}

export function poseToVec3(
  pose: WarehouseLivePose | null,
): [number, number, number] {
  if (!pose) return [0, 0, 0];
  return [pose.x_m, pose.y_m, pose.z_m];
}
