import type { WarehouseDeleteTarget } from "./components/WarehouseDeleteConfirmationDialog";

export type WarehousePageMode = "idle" | "setup" | "checks" | "mission";

export type WarehousePageState = {
  mode: WarehousePageMode;
  setupTab: "map" | "rig" | "dock" | "defaults";
  mapDetailTab: "layers" | "coordinateSetup";
  deleteTarget: WarehouseDeleteTarget;
};

export type WarehousePageAction =
  | { type: "open-mode"; mode: Exclude<WarehousePageMode, "idle"> }
  | { type: "close-mode" }
  | { type: "set-setup-tab"; tab: WarehousePageState["setupTab"] }
  | { type: "set-map-detail-tab"; tab: WarehousePageState["mapDetailTab"] }
  | { type: "request-delete"; target: NonNullable<WarehouseDeleteTarget> }
  | { type: "cancel-delete" };

export const initialWarehousePageState: WarehousePageState = {
  mode: "idle",
  setupTab: "map",
  mapDetailTab: "layers",
  deleteTarget: null,
};

export function warehousePageReducer(
  state: WarehousePageState,
  action: WarehousePageAction,
): WarehousePageState {
  switch (action.type) {
    case "open-mode":
      return { ...state, mode: action.mode };
    case "close-mode":
      return { ...state, mode: "idle" };
    case "set-setup-tab":
      return { ...state, setupTab: action.tab };
    case "set-map-detail-tab":
      return { ...state, mapDetailTab: action.tab };
    case "request-delete":
      return { ...state, deleteTarget: action.target };
    case "cancel-delete":
      return { ...state, deleteTarget: null };
    default:
      return state;
  }
}
