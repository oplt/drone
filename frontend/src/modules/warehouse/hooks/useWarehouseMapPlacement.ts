import { useCallback, useEffect, useMemo, useState } from "react";
import {
  computeWarehouseScanPose,
  listWarehouseScanTargets,
  type WarehouseLocalPose,
  type WarehouseScanTarget,
} from "../api/warehouseInspectionApi";
import {
  type MapPlacementPoint,
  shelfNormalFromFacing,
  WAREHOUSE_MAP_FRAME_ID,
} from "../utils/warehouseMapPlacement";

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
  const [shelfFacing, setShelfFacing] = useState("+y");
  const [standoffM, setStandoffM] = useState(1.2);
  const [draftTarget, setDraftTarget] = useState<MapPlacementPoint | null>(null);
  const [draftScanPose, setDraftScanPose] = useState<WarehouseLocalPose | null>(
    null,
  );
  const [targets, setTargets] = useState<WarehouseScanTarget[]>([]);
  const [targetsLoading, setTargetsLoading] = useState(false);

  const refreshTargets = useCallback(async () => {
    if (warehouseMapId == null) {
      setTargets([]);
      return;
    }
    setTargetsLoading(true);
    try {
      const rows = await listWarehouseScanTargets(warehouseMapId, token);
      setTargets(rows);
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
    setDraftTarget(null);
    setDraftScanPose(null);
    setPickMode(false);
  }, [warehouseMapId]);

  const clearDraft = useCallback(() => {
    setDraftTarget(null);
    setDraftScanPose(null);
  }, []);

  const handlePick = useCallback((point: MapPlacementPoint) => {
    setDraftTarget(point);
  }, []);

  useEffect(() => {
    if (!draftTarget) {
      setDraftScanPose(null);
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const response = await computeWarehouseScanPose(
          {
            target_point: {
              frame_id: WAREHOUSE_MAP_FRAME_ID,
              x_m: draftTarget.x_m,
              y_m: draftTarget.y_m,
              z_m: draftTarget.z_m,
            },
            shelf_normal: shelfNormalFromFacing(shelfFacing),
            standoff_m: standoffM,
          },
          token,
        );
        if (!cancelled) {
          setDraftScanPose(response.scan_pose);
        }
      } catch (error) {
        if (!cancelled) {
          onError(
            error instanceof Error
              ? error.message
              : "Scan pose could not be computed for the picked point.",
          );
          setDraftScanPose(null);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [draftTarget, onError, shelfFacing, standoffM, token]);

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
      shelfFacing,
      standoffM,
      targets,
      targetsLoading,
    ],
  );

  return { viewerProps, panelProps };
}
