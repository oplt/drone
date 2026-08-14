import {
  connectWarehouseLiveMap,
  disconnectWarehouseLiveMap,
  fetchWarehouseLiveMapSnapshot,
} from "../api/warehouseLiveMapApi";
import {
  WAREHOUSE_LIVE_VOXEL_EMPTY_HEALTH,
  type WarehouseLiveVoxelConnectionState,
} from "./warehouseLiveVoxelMapConstants";
import { createWarehouseLiveVoxelMessageLoop } from "./warehouseLiveVoxelMapMessageLoop";
import {
  warehouseLiveMapReconnectDelayMs,
  warehouseLiveMapSnapshotPollDelayMs,
} from "./warehouseLiveVoxelMapTiming";
import type { WarehouseLiveVoxelMergedState } from "./warehouseLiveVoxelMapTypes";

export type WarehouseLiveVoxelTransportSetters = {
  setConnectionState: (
    value:
      | WarehouseLiveVoxelConnectionState
      | ((current: WarehouseLiveVoxelConnectionState) => WarehouseLiveVoxelConnectionState),
  ) => void;
  setChunksById: (value: Map<string, import("../api/warehouseLiveMapApi").WarehouseLiveVoxelChunk>) => void;
  setProvisionalCandidatesByKey: (
    value: Map<string, import("../api/warehouseLiveMapApi").WarehouseLiveProvisionalCandidate>,
  ) => void;
  setCoverageRepairHints: (
    value: import("../api/warehouseLiveMapApi").WarehouseCoverageRepairHint[],
  ) => void;
  setCoordinateState: (
    value: import("../api/warehouseLiveMapApi").WarehouseCoordinateLiveState | null,
  ) => void;
  setScanPath: (
    value: import("../api/warehouseLiveMapApi").WarehouseLiveMapUpdate["scan_path_sample"],
  ) => void;
  setLatestUpdate: (
    value: import("../api/warehouseLiveMapApi").WarehouseLiveMapUpdate | null,
  ) => void;
  setHealth: (value: import("../api/warehouseLiveMapApi").WarehouseLiveHealthFlags) => void;
  setError: (value: string | null) => void;
  setFinalizedScanJobId: (value: number | null) => void;
  setLastUpdateAt: (value: string | null) => void;
  setManifest: (
    value: import("../api/warehouseLiveMapApi").WarehouseLiveMapManifestSummary | null,
  ) => void;
};

type StartWarehouseLiveVoxelMapTransportArgs = {
  flightId: string;
  token?: string | null;
  streamPausedRef: { current: boolean };
  stateRef: { current: WarehouseLiveVoxelMergedState };
  setters: WarehouseLiveVoxelTransportSetters;
};

export function startWarehouseLiveVoxelMapTransport({
  flightId,
  token,
  streamPausedRef,
  stateRef,
  setters,
}: StartWarehouseLiveVoxelMapTransportArgs): () => void {
  let cancelled = false;
  let reconnectAttempt = 0;
  let snapshotPollAttempt = 0;
  let snapshotPollInFlight = false;
  let socket: WebSocket | null = null;
  let wsConnected = false;
  let reconnectTimer: number | null = null;
  let snapshotPollTimer: number | null = null;

  const messageLoop = createWarehouseLiveVoxelMessageLoop(streamPausedRef, stateRef, setters);

  const clearTimers = () => {
    if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
    if (snapshotPollTimer != null) window.clearTimeout(snapshotPollTimer);
    reconnectTimer = null;
    snapshotPollTimer = null;
    messageLoop.dispose();
  };

  function scheduleSnapshotPoll() {
    if (cancelled || wsConnected) return;
    snapshotPollAttempt += 1;
    if (snapshotPollTimer != null) window.clearTimeout(snapshotPollTimer);
    snapshotPollTimer = window.setTimeout(() => {
      snapshotPollTimer = null;
      pollSnapshot();
    }, warehouseLiveMapSnapshotPollDelayMs(snapshotPollAttempt));
  }

  function pollSnapshot() {
    if (cancelled || wsConnected || snapshotPollInFlight) return;
    snapshotPollInFlight = true;
    void fetchWarehouseLiveMapSnapshot(flightId, token)
      .then((snapshot) => {
        if (!cancelled && !wsConnected) messageLoop.applyMessage(snapshot);
      })
      .catch(() => {
        /* websocket remains primary transport */
      })
      .finally(() => {
        snapshotPollInFlight = false;
        scheduleSnapshotPoll();
      });
  }

  const openSocket = () => {
    if (cancelled) return;
    setters.setConnectionState(reconnectAttempt > 0 ? "reconnecting" : "connecting");
    socket = connectWarehouseLiveMap(flightId, {
      onOpen: () => {
        reconnectAttempt = 0;
        snapshotPollAttempt = 0;
        wsConnected = true;
        if (snapshotPollTimer != null) {
          window.clearTimeout(snapshotPollTimer);
          snapshotPollTimer = null;
        }
        setters.setError(null);
        setters.setConnectionState("live");
        messageLoop.scheduleStaleCheck();
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "ping" }));
        }
      },
      onMessage: messageLoop.applyMessage,
      onError: () => {
        setters.setError("Live voxel stream error.");
      },
      onClose: () => {
        wsConnected = false;
        if (cancelled) return;
        reconnectAttempt += 1;
        setters.setConnectionState((current) =>
          current === "finalized" ? current : "reconnecting",
        );
        pollSnapshot();
        reconnectTimer = window.setTimeout(
          openSocket,
          warehouseLiveMapReconnectDelayMs(reconnectAttempt),
        );
      },
    });
  };

  pollSnapshot();
  openSocket();

  return () => {
    cancelled = true;
    wsConnected = false;
    clearTimers();
    disconnectWarehouseLiveMap(socket);
    socket = null;
  };
}

export function resetWarehouseLiveVoxelMapState(setters: WarehouseLiveVoxelTransportSetters) {
  setters.setConnectionState("empty");
  setters.setChunksById(new Map());
  setters.setProvisionalCandidatesByKey(new Map());
  setters.setCoverageRepairHints([]);
  setters.setCoordinateState(null);
  setters.setScanPath([]);
  setters.setLatestUpdate(null);
  setters.setHealth(WAREHOUSE_LIVE_VOXEL_EMPTY_HEALTH);
  setters.setError(null);
  setters.setFinalizedScanJobId(null);
  setters.setLastUpdateAt(null);
  setters.setManifest(null);
}
