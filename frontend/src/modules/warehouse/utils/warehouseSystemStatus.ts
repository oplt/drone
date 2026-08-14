import type { WarehouseUiStatus } from "../components/WarehouseStatusBadge";

export type WarehouseSystemStatusItem = {
  label: string;
  value: string;
  status: WarehouseUiStatus;
};

type BuildSystemStatusInput = {
  droneConnected: boolean;
  wsConnected: boolean;
  viewingScanReplay: boolean;
  scannedMapReplayHasData: boolean;
  activeFlightId: string | null;
  liveChunkCount: number;
  warehousePreflightPassed: boolean;
  missionState: string;
};

export function buildWarehouseSystemStatusItems(
  input: BuildSystemStatusInput,
): WarehouseSystemStatusItem[] {
  const {
    droneConnected,
    wsConnected,
    viewingScanReplay,
    scannedMapReplayHasData,
    activeFlightId,
    liveChunkCount,
    warehousePreflightPassed,
    missionState,
  } = input;

  return [
    {
      label: "Drone",
      value: droneConnected ? "Online" : "Offline",
      status: droneConnected ? "ready" : "blocked",
    },
    {
      label: "Link",
      value: wsConnected ? "Secure" : "Lost",
      status: wsConnected ? "ready" : "blocked",
    },
    {
      label: "Map",
      value: viewingScanReplay
        ? scannedMapReplayHasData
          ? "Replay"
          : "Empty"
        : activeFlightId
          ? liveChunkCount > 0
            ? "Live"
            : "Streaming"
          : "None",
      status: viewingScanReplay
        ? scannedMapReplayHasData
          ? "ready"
          : "waiting"
        : activeFlightId
          ? liveChunkCount > 0
            ? "ready"
            : "running"
          : "unknown",
    },
    {
      label: "Preflight",
      value: warehousePreflightPassed ? "Ready" : "Blocked",
      status: warehousePreflightPassed ? "ready" : "blocked",
    },
    {
      label: "Control",
      value: missionState === "running" ? "Active" : "Idle",
      status: missionState === "running" ? "running" : "unknown",
    },
  ];
}

export function buildStartScanTooltip(input: {
  warehousePreflightPassed: boolean;
  selectedWarehouseMapId: number | null;
  selectedSensorRigId: number | null;
  sensorRigReady: boolean | undefined;
  perceptionReady: boolean | undefined;
}): string {
  if (!input.warehousePreflightPassed) {
    return "Run preflight checks and wait for them to pass before starting flight.";
  }
  if (!input.selectedWarehouseMapId) {
    return "Select a warehouse map to enable launch.";
  }
  if (input.selectedSensorRigId == null || input.sensorRigReady !== true) {
    return "Select a registered sensor rig before starting.";
  }
  if (!input.perceptionReady) {
    return "Launch scan — mapping stack and nvblox start with the flight.";
  }
  return `Scan warehouse map #${input.selectedWarehouseMapId}.`;
}
