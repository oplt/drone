import { MissionPreflightPanel } from "../../mission-runtime";
import { MissionCommandPanel } from "../../mission-runtime/components/MissionCommandPanel";
import { TaskPreflightCommandsDrawer } from "../../mission-workflow";
import type { ControlledFlightPageSession } from "../hooks/useControlledFlightPageSession";

type ControlledFlightPageDrawersSectionProps = {
  session: ControlledFlightPageSession;
};

export function ControlledFlightPageDrawersSection({
  session,
}: ControlledFlightPageDrawersSectionProps) {
  const { apiBase, preflightCommandsDrawer, runtime, missionLauncher } = session;

  return (
    <TaskPreflightCommandsDrawer
      open={preflightCommandsDrawer.open}
      onOpenChange={preflightCommandsDrawer.onOpenChange}
    >
      <MissionPreflightPanel
        apiBase={apiBase}
        missionType="controlled"
        preflightRun={missionLauncher.preflightRun}
        telemetry={runtime.telemetry}
      />
      <MissionCommandPanel
        telemetry={runtime.telemetry}
        droneConnected={runtime.droneConnected}
        missionStatus={runtime.missionStatus}
        activeFlightId={runtime.activeFlightId}
        apiBase={apiBase}
      />
    </TaskPreflightCommandsDrawer>
  );
}
