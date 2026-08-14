import { useCallback } from "react";
import { useTaskPreflightCommandsDrawer } from "../../mission-workflow";

export type WarehouseDrawerKey = "setup" | "checks" | "mission";

export function useWarehouseDrawerCoordinator() {
  const setup = useTaskPreflightCommandsDrawer();
  const checks = useTaskPreflightCommandsDrawer();
  const mission = useTaskPreflightCommandsDrawer();

  const closeOthers = useCallback(
    (except: WarehouseDrawerKey) => {
      if (except !== "setup") setup.closeDrawer();
      if (except !== "checks") checks.closeDrawer();
      if (except !== "mission") mission.closeDrawer();
    },
    [checks, mission, setup],
  );

  const onSetupOpenChange = useCallback(
    (open: boolean) => {
      setup.onOpenChange(open);
      if (open) closeOthers("setup");
    },
    [closeOthers, setup],
  );

  const onChecksOpenChange = useCallback(
    (open: boolean) => {
      checks.onOpenChange(open);
      if (open) closeOthers("checks");
    },
    [checks, closeOthers],
  );

  const onMissionOpenChange = useCallback(
    (open: boolean) => {
      mission.onOpenChange(open);
      if (open) closeOthers("mission");
    },
    [closeOthers, mission],
  );

  return {
    setup,
    checks,
    mission,
    onSetupOpenChange,
    onChecksOpenChange,
    onMissionOpenChange,
  };
}
