import { useCallback, useEffect, useMemo, useState } from "react";
import {
  listWarehouseScanTargets,
  fetchActiveWarehouseCoordinateFrame,
  type WarehouseCoordinateFrame,
  type WarehouseLocalPose,
  type WarehouseScanTarget,
} from "../api/warehouseInspectionApi";
import { type MapPlacementPoint } from "../utils/warehouseMapPlacement";
import { useWarehouseScanPoseDraft } from "./useWarehouseScanPoseDraft";

export type WarehouseMapPlacementViewerProps = {
  pickMode: boolean;
  placementZ: number;
  targets: WarehouseScanTarget[];
  draftTarget: MapPlacementPoint | null;
  draftScanPose: WarehouseLocalPose | null;
  onPick: (point: MapPlacementPoint) => void;
  coordinateFrame: WarehouseCoordinateFrame | null;
  pickBlockReason: string | null;
};

export type WarehouseMapPlacementPanelProps = {
  pickMode: boolean;
  placementZ: number;
  shelfFacing: string;
  standoffM: number;
  draftTarget: MapPlacementPoint | null;
  draftScanPose: WarehouseLocalPose | null;
  targets: WarehouseScanTarget[];
  targetsLoading: boolean;
  setPickMode: (enabled: boolean) => void;
  setPlacementZ: (value: number) => void;
  setShelfFacing: (value: string) => void;
  setStandoffM: (value: number) => void;
  refreshTargets: () => Promise<void>;
  clearDraft: () => void;
  pickBlockReason: string | null;
  coordinateFrame: WarehouseCoordinateFrame | null;
};

export function useWarehouseMapPlacement({
  warehouseMapId,
  token,
  onError,
}: {
  warehouseMapId: number | null;
  token?: string | null;
  onError: (message: string) => void;
}) {
  const [pickMode, setPickMode] = useState(false);
  const [placementZ, setPlacementZ] = useState(1.6);
  const [targets, setTargets] = useState<WarehouseScanTarget[]>([]);
  const [targetsLoading, setTargetsLoading] = useState(false);
  const [coordinateFrame, setCoordinateFrame] = useState<WarehouseCoordinateFrame | null>(null);
  const [coordinateFrameLoading, setCoordinateFrameLoading] = useState(false);
  const {
    shelfFacing,
    standoffM,
    draftTarget,
    draftScanPose,
    setShelfFacing,
    setStandoffM,
    setDraftTarget,
    clearDraft,
  } = useWarehouseScanPoseDraft({ token, onError });

  const refreshTargets = useCallback(async () => {
    if (warehouseMapId == null) {
      setTargets([]);
      return;
    }
    setTargetsLoading(true);
    try {
      const pageSize = 200;
      let offset = 0;
      let total = 0;
      const all: WarehouseScanTarget[] = [];
      do {
        const page = await listWarehouseScanTargets(warehouseMapId, token, {
          limit: pageSize,
          offset,
          active: true,
        });
        total = page.total;
        all.push(...page.items);
        offset += pageSize;
      } while (all.length < total);
      setTargets(all);
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Scan targets could not be loaded.",
      );
    } finally {
      setTargetsLoading(false);
    }
  }, [onError, token, warehouseMapId]);

  useEffect(() => {
    void refreshTargets();
  }, [refreshTargets]);

  useEffect(() => {
    let cancelled = false;
    if (warehouseMapId == null) {
      setCoordinateFrame(null);
      return;
    }
    setCoordinateFrameLoading(true);
    void fetchActiveWarehouseCoordinateFrame(warehouseMapId, token)
      .then((frame) => {
        if (!cancelled) setCoordinateFrame(frame);
      })
      .catch(() => {
        if (!cancelled) setCoordinateFrame(null);
      })
      .finally(() => {
        if (!cancelled) setCoordinateFrameLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, warehouseMapId]);

  const pickBlockReason = coordinateFrameLoading
    ? "Loading coordinate-frame revision."
    : coordinateFrame == null
      ? "Lock warehouse localization before placing targets."
      : null;

  const updatePickMode = useCallback(
    (enabled: boolean) => {
      if (enabled && pickBlockReason) {
        setPickMode(false);
        onError(pickBlockReason);
        return;
      }
      setPickMode(enabled);
    },
    [onError, pickBlockReason],
  );

  useEffect(() => {
    if (pickBlockReason) {
      setPickMode(false);
      clearDraft();
    }
  }, [clearDraft, pickBlockReason]);

  useEffect(() => {
    clearDraft();
    setPickMode(false);
  }, [clearDraft, warehouseMapId]);

  const handlePick = useCallback((point: MapPlacementPoint) => {
    setDraftTarget(point);
  }, [setDraftTarget]);

  const viewerProps = useMemo<WarehouseMapPlacementViewerProps>(
    () => ({
      pickMode,
      placementZ,
      targets,
      draftTarget,
      draftScanPose,
      onPick: handlePick,
      coordinateFrame,
      pickBlockReason,
    }),
    [
      draftScanPose,
      draftTarget,
      handlePick,
      pickMode,
      placementZ,
      targets,
      coordinateFrame,
      pickBlockReason,
    ],
  );

  const panelProps = useMemo<WarehouseMapPlacementPanelProps>(
    () => ({
      pickMode,
      placementZ,
      shelfFacing,
      standoffM,
      draftTarget,
      draftScanPose,
      targets,
      targetsLoading,
      setPickMode: updatePickMode,
      setPlacementZ,
      setShelfFacing,
      setStandoffM,
      refreshTargets,
      clearDraft,
      pickBlockReason,
      coordinateFrame,
    }),
    [
      clearDraft,
      draftScanPose,
      draftTarget,
      pickMode,
      placementZ,
      refreshTargets,
      setShelfFacing,
      setStandoffM,
      shelfFacing,
      standoffM,
      targets,
      targetsLoading,
      pickBlockReason,
      coordinateFrame,
      updatePickMode,
    ],
  );

  return { viewerProps, panelProps };
}
