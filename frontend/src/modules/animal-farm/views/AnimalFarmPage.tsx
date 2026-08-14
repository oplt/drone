import { useAnimalFarmPageSession } from "../hooks/useAnimalFarmPageSession";
import { AnimalFarmHerdPanel } from "../sections/AnimalFarmHerdPanel";
import { AnimalFarmPageDrawersSection } from "../sections/AnimalFarmPageDrawersSection";
import { AnimalFarmPageMainSection } from "../sections/AnimalFarmPageMainSection";

export default function AnimalFarmPage() {
  const session = useAnimalFarmPageSession();

  return (
    <>
      <AnimalFarmHerdPanel
        herds={session.herds.herds}
        selectedHerdId={session.herds.selectedHerdId}
        onSelectedHerdIdChange={session.herds.setSelectedHerdId}
        loadingHerdOps={session.herds.loadingHerdOps}
        collarIdForSearch={session.herds.collarIdForSearch}
        onCollarIdForSearchChange={session.herds.setCollarIdForSearch}
        onCreateTask={session.herds.createTaskAndPlan}
        onRefreshPositions={() =>
          session.herds.selectedHerdId &&
          void session.herds.fetchLatestPositions(session.herds.selectedHerdId)
        }
        onRefreshRisk={() =>
          session.herds.selectedHerdId && void session.herds.fetchRisk(session.herds.selectedHerdId)
        }
        herdAlerts={session.herds.herdAlerts}
      />
      <AnimalFarmPageMainSection session={session} />
      <AnimalFarmPageDrawersSection session={session} />
    </>
  );
}
