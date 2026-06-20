import { useCallback, useEffect, useMemo, useState } from "react";
import {
  listWarehouseScanTargets,
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
    }),
    [
      draftScanPose,
      draftTarget,
      handlePick,
      pickMode,
      placementZ,
      targets,
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
      setPickMode,
      setPlacementZ,
      setShelfFacing,
      setStandoffM,
      refreshTargets,
      clearDraft,
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
    ],
  );

  return { viewerProps, panelProps };
}
