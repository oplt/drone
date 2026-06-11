import type {
  WarehouseLivePose,
  WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";
import { chunkStateKey } from "./liveMapChunkRetention";

export type LiveMapRenderChunk = {
  id: string;
  stateKey: string;
  kind: WarehouseLiveVoxelChunk["kind"];
  sequence: number;
  center: [number, number, number];
  size: [number, number, number];
  pointCount: number;
  hasGeometry: boolean;
  previewPoints: [number, number, number][];
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

function normalizePreviewPoints(
  raw: WarehouseLiveVoxelChunk["preview_points_m"],
): [number, number, number][] {
  if (!Array.isArray(raw)) return [];
  const points: [number, number, number][] = [];
  for (const entry of raw) {
    if (!Array.isArray(entry) || entry.length < 3) continue;
    const x = Number(entry[0]);
    const y = Number(entry[1]);
    const z = Number(entry[2]);
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
      continue;
    }
    points.push([x, y, z]);
  }
  return points;
}

export function toRenderChunks(
  chunks: WarehouseLiveVoxelChunk[],
): LiveMapRenderChunk[] {
  return chunks.map((chunk, index) => {
    const bbox =
      Array.isArray(chunk.bbox_local_m) && chunk.bbox_local_m.length === 6
        ? chunk.bbox_local_m
        : null;
    const previewPoints = normalizePreviewPoints(chunk.preview_points_m);
    const ring = 1 + Math.floor(index / 20);
    const angle = index * 0.91;
    const fallbackCenter: [number, number, number] = [
      Math.cos(angle) * ring,
      Math.sin(angle) * ring,
      chunk.kind === "point_cloud" ? 0.35 : 0.6,
    ];
    const centerFromPreview = previewPoints.length
      ? previewPoints.reduce<[number, number, number]>(
          (acc, point) => [
            acc[0] + point[0],
            acc[1] + point[1],
            acc[2] + point[2],
          ],
          [0, 0, 0],
        )
      : null;
    const center: [number, number, number] = bbox
      ? centerFromBbox(bbox)
      : centerFromPreview
        ? [
            centerFromPreview[0] / previewPoints.length,
            centerFromPreview[1] / previewPoints.length,
            centerFromPreview[2] / previewPoints.length,
          ]
        : fallbackCenter;
    return {
      id: chunk.id,
      stateKey: chunkStateKey(chunk),
      kind: chunk.kind,
      sequence: chunk.sequence ?? index,
      center,
      size: bbox ? sizeFromBbox(bbox) : [0.28, 0.28, 0.28],
      pointCount: chunk.point_count ?? previewPoints.length,
      hasGeometry:
        Boolean(chunk.url) ||
        (chunk.point_count ?? 0) > 0 ||
        previewPoints.length > 0,
      previewPoints,
    };
  });
}

export function poseToVec3(
  pose: WarehouseLivePose | null,
): [number, number, number] {
  if (!pose) return [0, 0, 0];
  return [pose.x_m, pose.y_m, pose.z_m];
}
