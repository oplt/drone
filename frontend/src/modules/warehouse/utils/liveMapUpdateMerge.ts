import {
  isWarehouseLiveMapSnapshot,
  isWarehouseLiveMapUpdate,
  type WarehouseLiveMapMessage,
  type WarehouseLiveMapUpdate,
  type WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";

const MAX_PATH_POINTS = 600;

export type WarehouseLiveMapAccumulator = {
  chunksById: Map<string, WarehouseLiveVoxelChunk>;
  scanPath: WarehouseLiveMapUpdate["scan_path_sample"];
  flightId: string | null;
};

type WarehouseLiveMapMergeState = Omit<WarehouseLiveMapAccumulator, "flightId"> & {
  flightId?: string | null;
};

/**
 * Chunk IDs are canonical within one flight. Different IDs accumulate, the
 * same ID replaces its prior revision, and a flight change starts fresh.
 */
export function mergeUpdate(
  current: WarehouseLiveMapMergeState,
  update: WarehouseLiveMapUpdate,
): WarehouseLiveMapAccumulator {
  const sameFlight = !current.flightId || current.flightId === update.flight_id;
  const chunksById = new Map(
    sameFlight ? current.chunksById : new Map<string, WarehouseLiveVoxelChunk>(),
  );

  for (const id of update.removed_chunk_ids) {
    chunksById.delete(id);
    for (const key of [...chunksById.keys()]) {
      if (key.endsWith(`:${id}`)) chunksById.delete(key);
    }
  }
  for (const chunk of update.changed_chunks) {
    const existing = chunksById.get(chunk.id);
    const unchanged =
      existing &&
      existing.url === chunk.url &&
      existing.byte_size === chunk.byte_size &&
      existing.checksum_sha256 === chunk.checksum_sha256;
    if (!unchanged) chunksById.set(chunk.id, chunk);
  }

  return {
    chunksById,
    scanPath: [
      ...(sameFlight ? current.scanPath : []),
      ...update.scan_path_sample,
    ].slice(-MAX_PATH_POINTS),
    flightId: update.flight_id,
  };
}

export function applyWarehouseLiveMapMessage(
  current: WarehouseLiveMapMergeState,
  message: WarehouseLiveMapMessage,
): WarehouseLiveMapAccumulator {
  if (isWarehouseLiveMapSnapshot(message)) {
    return message.updates.reduce<WarehouseLiveMapAccumulator>(
      (accumulator, update) => mergeUpdate(accumulator, update),
      { ...current, flightId: current.flightId ?? null },
    );
  }
  return isWarehouseLiveMapUpdate(message)
    ? mergeUpdate(current, message)
    : { ...current, flightId: current.flightId ?? null };
}
