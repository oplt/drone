import { useEffect } from "react";
import { disconnectWarehouseLiveMap } from "../api/warehouseLiveMapApi";
import {
  resetWarehouseLiveVoxelMapState,
  startWarehouseLiveVoxelMapTransport,
  type WarehouseLiveVoxelTransportSetters,
} from "../utils/warehouseLiveVoxelMapTransportSession";
import type { WarehouseLiveVoxelMergedState } from "../utils/warehouseLiveVoxelMapTypes";

type UseWarehouseLiveVoxelMapTransportArgs = {
  flightId: string | null | undefined;
  enabled: boolean;
  token?: string | null;
  streamPausedRef: React.RefObject<boolean>;
  stateRef: React.MutableRefObject<WarehouseLiveVoxelMergedState>;
  setters: WarehouseLiveVoxelTransportSetters;
};

export function useWarehouseLiveVoxelMapTransport({
  flightId,
  enabled,
  token,
  streamPausedRef,
  stateRef,
  setters,
}: UseWarehouseLiveVoxelMapTransportArgs) {
  useEffect(() => {
    if (typeof window === "undefined") return;

    if (!flightId) {
      const resetTimer = window.setTimeout(() => resetWarehouseLiveVoxelMapState(setters), 0);
      return () => window.clearTimeout(resetTimer);
    }

    if (!enabled) {
      disconnectWarehouseLiveMap(null);
      const staleTimer = window.setTimeout(() => {
        setters.setConnectionState((current) => (current === "live" ? "stale" : current));
      }, 0);
      return () => window.clearTimeout(staleTimer);
    }

    return startWarehouseLiveVoxelMapTransport({
      flightId,
      token,
      streamPausedRef,
      stateRef,
      setters,
    });
  }, [enabled, flightId, setters, stateRef, streamPausedRef, token]);
}
