import { Box, Paper, Stack, Tab, Tabs, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { ErrorAlerts } from "../../../shared/ui/ErrorAlerts";
import { WarehouseFlightReadinessRibbon } from "../components/WarehouseFlightReadinessRibbon";
import type { WarehouseMappingRuntimeStatus } from "../components/WarehouseMappingHealthPanel";
import { WarehouseSystemStatusStrip } from "../components/WarehouseDashboardUi";
import type { WarehouseLiveHealthFlags } from "../api/warehouseLiveMapApi";
import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";
import type { WarehouseSensorRigHealth } from "../types";

import type { WarehouseSystemStatusItem } from "../utils/warehouseSystemStatus";

type WarehousePageShellProps = {
  systemStatusItems: WarehouseSystemStatusItem[];
  hasMap: boolean;
  hasRig: boolean;
  hasDock: boolean;
  preflight: WarehouseGoPreflight | null;
  droneConnected: boolean;
  activeFlightId: string | null;
  sensorRigHealth: WarehouseSensorRigHealth | null;
  mappingStatus: WarehouseMappingRuntimeStatus | null | undefined;
  liveHealth: WarehouseLiveHealthFlags | null | undefined;
  errors: string[];
  onDismissError: (index: number) => void;
  onClearErrors: () => void;
  mobileLayout: boolean;
  mobileTab: "status" | "scene" | "config";
  onMobileTabChange: (tab: "status" | "scene" | "config") => void;
  statusPane: ReactNode;
  scenePane: ReactNode;
  mobileConfigPane: ReactNode | null;
};

export function WarehousePageShell({
  systemStatusItems,
  hasMap,
  hasRig,
  hasDock,
  preflight,
  droneConnected,
  activeFlightId,
  sensorRigHealth,
  mappingStatus,
  liveHealth,
  errors,
  onDismissError,
  onClearErrors,
  mobileLayout,
  mobileTab,
  onMobileTabChange,
  statusPane,
  scenePane,
  mobileConfigPane,
}: WarehousePageShellProps) {
  return (
    <Paper
      sx={{
        width: "100%",
        p: 3,
        borderRadius: 3,
        backgroundColor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <Stack
        direction={{ xs: "column", md: "row" }}
        alignItems={{ xs: "flex-start", md: "center" }}
        justifyContent="space-between"
        sx={{ mb: 2 }}
        spacing={1}
      >
        <Box>
          <Typography
            variant="h5"
            sx={{ fontWeight: 600, fontSize: { xs: "1.3rem", md: "1.5rem" } }}
          >
            Warehouse Operations
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Autonomous indoor scan, live telemetry, and 3D mapping
          </Typography>
        </Box>
      </Stack>

      <Box sx={{ mb: 2 }}>
        <WarehouseSystemStatusStrip items={systemStatusItems} />
      </Box>

      <Box sx={{ mb: 2 }}>
        <WarehouseFlightReadinessRibbon
          hasMap={hasMap}
          hasRig={hasRig}
          hasDock={hasDock}
          preflight={preflight}
          droneConnected={droneConnected}
          activeFlightId={activeFlightId}
          sensorRigHealth={sensorRigHealth}
          mappingStatus={mappingStatus}
          liveHealth={liveHealth}
        />
      </Box>

      <ErrorAlerts
        errors={errors}
        onDismiss={onDismissError}
        onClearAll={onClearErrors}
      />

      {mobileLayout ? (
        <Tabs
          value={mobileTab}
          onChange={(_, value: "status" | "scene" | "config") =>
            onMobileTabChange(value)
          }
          variant="fullWidth"
          sx={{ mb: 1.5 }}
          aria-label="Warehouse mobile sections"
        >
          <Tab value="status" label="Status" />
          <Tab value="scene" label="Scene" />
          <Tab value="config" label="Config" />
        </Tabs>
      ) : null}

      <Stack
        sx={{
          minWidth: 0,
          width: "100%",
          display:
            !mobileLayout || mobileTab === "status" || mobileTab === "scene"
              ? "flex"
              : "none",
        }}
        spacing={2}
      >
        {!mobileLayout || mobileTab === "status" ? statusPane : null}
        {!mobileLayout || mobileTab === "scene" ? scenePane : null}
      </Stack>

      {mobileLayout && mobileTab === "config" ? mobileConfigPane : null}
    </Paper>
  );
}
