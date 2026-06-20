import type { ComponentProps, Dispatch, SetStateAction } from "react";
import { Alert, Stack, Tab, Tabs } from "@mui/material";
import { WarehouseDrawerSection } from "./WarehouseDrawerSection";
import { WarehouseExplorationPanel } from "./WarehouseExplorationPanel";
import { WarehouseFlightReadinessPanel } from "./WarehouseFlightReadinessPanel";
import { WarehouseManualMappingPanel } from "./WarehouseManualMappingPanel";
import { WarehouseMissionStatusSummary } from "./WarehouseMissionStatusSummary";
import { WarehouseProductScanFlyPanel } from "./WarehouseProductScanFlyPanel";

export type WarehouseFlyMode = "automated" | "productScan" | "manual";

type WarehouseFlyDrawerContentProps = {
  flyMode: WarehouseFlyMode;
  setFlyMode: Dispatch<SetStateAction<WarehouseFlyMode>>;
  preflightPassed: boolean;
  missionStatusProps: ComponentProps<typeof WarehouseMissionStatusSummary>;
  readinessProps: ComponentProps<typeof WarehouseFlightReadinessPanel>;
  explorationProps: ComponentProps<typeof WarehouseExplorationPanel>;
  productScanProps: ComponentProps<typeof WarehouseProductScanFlyPanel>;
  manualMappingProps: ComponentProps<typeof WarehouseManualMappingPanel>;
};

export function WarehouseFlyDrawerContent({
  flyMode,
  setFlyMode,
  preflightPassed,
  missionStatusProps,
  readinessProps,
  explorationProps,
  productScanProps,
  manualMappingProps,
}: WarehouseFlyDrawerContentProps) {
  return (
    <Stack spacing={2}>
      <WarehouseDrawerSection
        title="Mission Status"
        info="Live mission state from the warehouse scan runtime."
      >
        <WarehouseMissionStatusSummary {...missionStatusProps} />
      </WarehouseDrawerSection>

      <Tabs
        value={flyMode}
        onChange={(_, value: WarehouseFlyMode) => setFlyMode(value)}
        variant="fullWidth"
      >
        <Tab value="automated" label="Automated" disabled={!preflightPassed} />
        <Tab value="productScan" label="Product Scan" disabled={!preflightPassed} />
        <Tab value="manual" label="Manual" disabled={!preflightPassed} />
      </Tabs>

      {!preflightPassed && (
        <Alert severity="warning">
          Open Checks, run preflight, and wait for checks to pass before choosing a flight mode.
        </Alert>
      )}

      {preflightPassed && flyMode === "automated" && (
        <>
          <WarehouseDrawerSection
            title="Flight & Scan"
            info="Start the warehouse flight and scan using the selected setup map, dock, rig, and mission defaults."
          >
            <WarehouseFlightReadinessPanel {...readinessProps} />
          </WarehouseDrawerSection>
          <WarehouseDrawerSection
            title="Exploration"
            info="Frontier mode uses the ROS nvblox ESDF map and returns before reserve battery."
          >
            <WarehouseExplorationPanel {...explorationProps} />
          </WarehouseDrawerSection>
        </>
      )}

      {preflightPassed && flyMode === "productScan" && (
        <WarehouseDrawerSection
          title="Product Scan Flight"
          info="Select saved bin targets and create a warehouse product scan mission."
          showDivider={false}
        >
          <WarehouseProductScanFlyPanel {...productScanProps} />
        </WarehouseDrawerSection>
      )}

      {preflightPassed && flyMode === "manual" && (
        <WarehouseDrawerSection
          title="Manual Warehouse Mapping"
          info="Start a controlled keyboard flight, start ROS mapping, fly the inbound area manually, then stop mapping after landing."
          showDivider={false}
        >
          <WarehouseManualMappingPanel {...manualMappingProps} />
        </WarehouseDrawerSection>
      )}
    </Stack>
  );
}
