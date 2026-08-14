import ChecklistRoundedIcon from "@mui/icons-material/ChecklistRounded";
import { TaskPreflightCommandsDrawer } from "../../mission-workflow";
import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";
import { WarehousePreflightChecksPanel } from "../components/WarehousePreflightChecksPanel";

type WarehouseChecksDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preflight: WarehouseGoPreflight | null;
  running: boolean;
  error: string | null;
  onRunChecks: () => void;
};

export function WarehouseChecksDrawer({
  open,
  onOpenChange,
  preflight,
  running,
  error,
  onRunChecks,
}: WarehouseChecksDrawerProps) {
  return (
    <TaskPreflightCommandsDrawer
      open={open}
      onOpenChange={onOpenChange}
      title="Warehouse Checks"
      subtitle="Preflight readiness and system diagnostics"
      tabLabel="CHECKS"
      tabIcon={<ChecklistRoundedIcon fontSize="small" />}
      edgeTabIndex={1}
      edgeTabCount={3}
      paperSx={{ width: { xs: "min(100vw, 520px)", sm: 540, md: 560 } }}
    >
      <WarehousePreflightChecksPanel
        preflight={preflight}
        running={running}
        error={error}
        onRunChecks={() => {
          onRunChecks();
        }}
      />
    </TaskPreflightCommandsDrawer>
  );
}
