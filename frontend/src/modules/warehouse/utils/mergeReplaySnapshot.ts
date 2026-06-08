import type {
  WarehouseLiveMapSnapshot,
  WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";

export function mergeReplaySnapshot(snapshot: WarehouseLiveMapSnapshot): {
  chunks: WarehouseLiveVoxelChunk[];
  scanPath: WarehouseLiveMapSnapshot["updates"][number]["scan_path_sample"];
  latestUpdate: WarehouseLiveMapSnapshot["updates"][number] | null;
} {
  const chunksById = new Map<string, WarehouseLiveVoxelChunk>();
  let scanPath: WarehouseLiveMapSnapshot["updates"][number]["scan_path_sample"] =
    [];

  for (const update of snapshot.updates) {
    for (const id of update.removed_chunk_ids) {
      chunksById.delete(id);
    }
    for (const chunk of update.changed_chunks) {
      chunksById.set(chunk.id, chunk);
    }
    scanPath = [...scanPath, ...update.scan_path_sample];
  }

  return {
    chunks: Array.from(chunksById.values()).sort(
      (left, right) => (left.sequence ?? 0) - (right.sequence ?? 0),
    ),
    scanPath,
    latestUpdate: snapshot.updates.at(-1) ?? null,
  };
}
