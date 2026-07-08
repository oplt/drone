import {
  isWarehouseLiveMapSnapshot,
  isWarehouseLiveMapUpdate,
  type WarehouseLiveMapMessage,
  type WarehouseLiveMapUpdate,
  type WarehouseCoverageRepairHint,
  type WarehouseCoordinateLiveState,
  type WarehouseLiveProvisionalCandidate,
  type WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";

const MAX_PATH_POINTS = 600;

export type WarehouseLiveMapAccumulator = {
  chunksById: Map<string, WarehouseLiveVoxelChunk>;
  provisionalCandidatesByKey: Map<string, WarehouseLiveProvisionalCandidate>;
  coverageRepairHints: WarehouseCoverageRepairHint[];
  coordinateState: WarehouseCoordinateLiveState | null;
  scanPath: WarehouseLiveMapUpdate["scan_path_sample"];
  flightId: string | null;
};

type WarehouseLiveMapMergeState = {
  chunksById: Map<string, WarehouseLiveVoxelChunk>;
  provisionalCandidatesByKey?: Map<string, WarehouseLiveProvisionalCandidate>;
  coverageRepairHints?: WarehouseCoverageRepairHint[];
  coordinateState?: WarehouseCoordinateLiveState | null;
  scanPath: WarehouseLiveMapUpdate["scan_path_sample"];
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
  const provisionalCandidatesByKey = new Map(
    sameFlight
      ? current.provisionalCandidatesByKey ?? new Map<string, WarehouseLiveProvisionalCandidate>()
      : new Map<string, WarehouseLiveProvisionalCandidate>(),
  );
  for (const candidate of update.provisional_candidates ?? []) {
    if (candidate.inspection_ready === false) {
      provisionalCandidatesByKey.set(candidate.identity_key, candidate);
    }
  }

  return {
    chunksById,
    provisionalCandidatesByKey,
    coverageRepairHints: sameFlight
      ? [
          ...(current.coverageRepairHints ?? []),
          ...(update.coverage_repair_hints ?? []),
        ].slice(-100)
      : [...(update.coverage_repair_hints ?? [])].slice(-100),
    coordinateState: update.coordinate_state ?? current.coordinateState ?? null,
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
      {
        ...current,
        provisionalCandidatesByKey:
          current.provisionalCandidatesByKey ??
          new Map<string, WarehouseLiveProvisionalCandidate>(),
        coverageRepairHints: current.coverageRepairHints ?? [],
        coordinateState: current.coordinateState ?? null,
        flightId: current.flightId ?? null,
      },
    );
  }
  return isWarehouseLiveMapUpdate(message)
    ? mergeUpdate(current, message)
    : {
        chunksById: current.chunksById,
        provisionalCandidatesByKey:
          current.provisionalCandidatesByKey ??
          new Map<string, WarehouseLiveProvisionalCandidate>(),
        coverageRepairHints: current.coverageRepairHints ?? [],
        coordinateState: current.coordinateState ?? null,
        scanPath: current.scanPath,
        flightId: current.flightId ?? null,
      };
}
