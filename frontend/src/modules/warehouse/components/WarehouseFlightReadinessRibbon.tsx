import { Chip, Stack, Tooltip } from "@mui/material";
import type { WarehouseMappingRuntimeStatus } from "./WarehouseMappingHealthPanel";
import type { WarehouseSensorRigHealth } from "../types";
import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";
import type { WarehouseLiveHealthFlags } from "../api/warehouseLiveMapApi";

type RibbonItem = {
  key: string;
  label: string;
  ok: boolean;
  warn?: boolean;
  detail: string;
};

function colorFor(item: RibbonItem): "success" | "warning" | "default" {
  if (item.ok) return "success";
  if (item.warn) return "warning";
  return "default";
}

export function WarehouseFlightReadinessRibbon({
  hasMap,
  hasRig,
  hasDock,
  preflight,
  droneConnected,
  activeFlightId,
  sensorRigHealth,
  mappingStatus,
  liveHealth,
}: {
  hasMap: boolean;
  hasRig: boolean;
  hasDock: boolean;
  preflight: WarehouseGoPreflight | null;
  droneConnected: boolean;
  activeFlightId: string | null | undefined;
  sensorRigHealth: WarehouseSensorRigHealth | null;
  mappingStatus: WarehouseMappingRuntimeStatus | null | undefined;
  liveHealth?: WarehouseLiveHealthFlags | null;
}) {
  const items: RibbonItem[] = [
    {
      key: "map",
      label: hasMap ? "Map ready" : "Map missing",
      ok: hasMap,
      detail: hasMap
        ? "Warehouse footprint selected."
        : "Select a warehouse map in Setup.",
    },
    {
      key: "rig",
      label: sensorRigHealth?.ready
        ? "Rig ready"
        : hasRig
          ? "Rig blocked"
          : "Rig missing",
      ok: sensorRigHealth?.ready === true,
      warn: hasRig,
      detail: sensorRigHealth?.ready
        ? "Sensor rig calibration and readiness checks passed."
        : (sensorRigHealth?.blockers?.[0] ?? "Select a calibrated sensor rig."),
    },
    {
      key: "dock",
      label: hasDock ? "Dock set" : "No dock",
      ok: hasDock,
      warn: !hasDock,
      detail: hasDock
        ? "Dock station is selected for return and exploration."
        : "Dock is optional for scan flight, required for exploration.",
    },
    {
      key: "preflight",
      label: preflight?.ready_to_fly ? "Preflight OK" : "Preflight",
      ok: preflight?.ready_to_fly === true,
      warn: Boolean(preflight),
      detail:
        preflight?.blocking_reasons?.[0] ??
        preflight?.note ??
        "Run preflight checks.",
    },
    {
      key: "drone",
      label: droneConnected ? "Drone linked" : "Drone link",
      ok: droneConnected,
      detail: droneConnected
        ? "Telemetry reports a connected drone."
        : "Connect MAVLink telemetry.",
    },
    {
      key: "flight",
      label: activeFlightId ? "Flight active" : "No flight",
      ok: Boolean(activeFlightId),
      warn: !activeFlightId,
      detail: activeFlightId
        ? `Active flight ${activeFlightId}`
        : "No warehouse flight is active.",
    },
    {
      key: "manual",
      label: liveHealth?.mapping_recording
        ? "Recording"
        : mappingStatus?.ready
          ? "Stack running"
          : "Stack idle",
      ok:
        liveHealth?.mapping_recording === true || mappingStatus?.ready === true,
      warn: !mappingStatus?.ready,
      detail: liveHealth?.mapping_recording
        ? "Manual or automated mapping is recording voxel updates."
        : mappingStatus?.ready
          ? `Mapping stack status ${mappingStatus.status ?? "ready"}.`
          : (mappingStatus?.detail ??
            "Mapping stack starts with flight or manual mapping."),
    },
    {
      key: "control",
      label: activeFlightId ? "Control enabled" : "Control idle",
      ok: Boolean(activeFlightId),
      warn: !activeFlightId,
      detail: activeFlightId
        ? "Keyboard/manual control can be enabled for the active flight."
        : "Control becomes available after a flight starts.",
    },
  ];

  return (
    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
      {items.map((item) => (
        <Tooltip key={item.key} title={item.detail}>
          <Chip
            size="small"
            label={item.label}
            color={colorFor(item)}
            variant="outlined"
          />
        </Tooltip>
      ))}
    </Stack>
  );
}
