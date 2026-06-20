import { useCallback, useEffect, useState } from "react";

import {
  computeWarehouseScanPose,
  type WarehouseLocalPose,
} from "../api/warehouseInspectionApi";
import {
  type MapPlacementPoint,
  shelfNormalFromFacing,
  WAREHOUSE_MAP_FRAME_ID,
} from "../utils/warehouseMapPlacement";

const SCAN_POSE_DEBOUNCE_MS = 300;

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function useWarehouseScanPoseDraft({
  token,
  onError,
}: {
  token?: string | null;
  onError: (message: string) => void;
}) {
  const [shelfFacing, setShelfFacing] = useState("+y");
  const [standoffM, setStandoffM] = useState(1.2);
  const [draftTarget, setDraftTarget] = useState<MapPlacementPoint | null>(null);
  const [draftScanPose, setDraftScanPose] = useState<WarehouseLocalPose | null>(null);

  const clearDraft = useCallback(() => {
    setDraftTarget(null);
    setDraftScanPose(null);
  }, []);

  useEffect(() => {
    if (!draftTarget) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void computeWarehouseScanPose(
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
        controller.signal,
      )
        .then((response) => {
          if (!controller.signal.aborted) setDraftScanPose(response.scan_pose);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || isAbortError(error)) return;
          onError(
            error instanceof Error
              ? error.message
              : "Scan pose could not be computed for the picked point.",
          );
          setDraftScanPose(null);
        });
    }, SCAN_POSE_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [draftTarget, onError, shelfFacing, standoffM, token]);

  return {
    shelfFacing,
    standoffM,
    draftTarget,
    draftScanPose,
    setShelfFacing,
    setStandoffM,
    setDraftTarget,
    clearDraft,
  };
}
