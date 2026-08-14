import { MissionPreflightPanel } from "../../mission-runtime";
import { MissionCommandPanel } from "../../mission-runtime/components/MissionCommandPanel";
import { TaskPreflightCommandsDrawer } from "../../mission-workflow";
import type { AnimalFarmPageSession } from "../hooks/useAnimalFarmPageSession";

type AnimalFarmPageDrawersSectionProps = {
  session: AnimalFarmPageSession;
};

export function AnimalFarmPageDrawersSection({ session }: AnimalFarmPageDrawersSectionProps) {
  const { apiBase, preflightCommandsDrawer, runtime, missionPlanner } = session;

  return (
    <TaskPreflightCommandsDrawer
      open={preflightCommandsDrawer.open}
      onOpenChange={preflightCommandsDrawer.onOpenChange}
    >
      <MissionPreflightPanel
        apiBase={apiBase}
        missionType="route"
        preflightRun={missionPlanner.preflightRun}
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
