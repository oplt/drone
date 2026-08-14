import { useCallback, useMemo, useReducer, useRef, useState } from "react";
import { useMediaQuery, useTheme } from "@mui/material";
import type { MissionLifecycleState } from "../../mission-runtime";
import { getToken } from "../../session";
import type { WarehouseFlyMode } from "../components/WarehouseFlyDrawerContent";
import {
  initialWarehousePageState,
  warehousePageReducer,
  type WarehousePageState,
} from "../warehousePageState";
import { useWarehouseDrawerCoordinator } from "./useWarehouseDrawerCoordinator";

export function useWarehousePageUiState() {
  const [pageState, dispatchPage] = useReducer(
    warehousePageReducer,
    initialWarehousePageState,
  );
  const { setupTab, mapDetailTab, deleteTarget } = pageState;
  const setSetupTab = useCallback(
    (tab: WarehousePageState["setupTab"]) =>
      dispatchPage({ type: "set-setup-tab", tab }),
    [],
  );
  const setMapDetailTab = useCallback(
    (tab: WarehousePageState["mapDetailTab"]) =>
      dispatchPage({ type: "set-map-detail-tab", tab }),
    [],
  );
  const setDeleteTarget = useCallback(
    (target: WarehousePageState["deleteTarget"]) =>
      target
        ? dispatchPage({ type: "request-delete", target })
        : dispatchPage({ type: "cancel-delete" }),
    [],
  );

  const drawers = useWarehouseDrawerCoordinator();
  const theme = useTheme();
  const mobileLayout = useMediaQuery(theme.breakpoints.down("md"));
  const [mobileTab, setMobileTab] = useState<"status" | "scene" | "config">(
    "scene",
  );
  const [selectedDockId, setSelectedDockId] = useState<number | null>(null);
  const [flyMode, setFlyMode] = useState<WarehouseFlyMode>("automated");
  const viewerSectionRef = useRef<HTMLDivElement | null>(null);
  const previousMissionStateRef = useRef<MissionLifecycleState | null>(null);

  const authToken = getToken();
  const apiBase = (
    import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"
  ).replace(/\/$/, "");
  const localStorageKey = useMemo(
    () => `warehouse.ops.${authToken ? authToken.slice(-12) : "anonymous"}`,
    [authToken],
  );

  return {
    setupTab,
    mapDetailTab,
    deleteTarget,
    setSetupTab,
    setMapDetailTab,
    setDeleteTarget,
    drawers,
    mobileLayout,
    mobileTab,
    setMobileTab,
    selectedDockId,
    setSelectedDockId,
    flyMode,
    setFlyMode,
    viewerSectionRef,
    previousMissionStateRef,
    authToken,
    apiBase,
    localStorageKey,
  };
}
