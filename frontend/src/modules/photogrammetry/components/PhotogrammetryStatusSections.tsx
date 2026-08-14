import {
  MissionFlightStatusPanel,
  MissionWaypointList,
  type MissionStatus,
  type Waypoint,
} from "../../mission-workflow";

export function PhotogrammetryStatusSections({
  waypoints,
  alt,
  missionStatus,
  activeFlightId,
  wsConnected,
  selectedWaypointIndex = null,
  onSelectWaypoint,
  lastPacketAgeSec = null,
}: {
  waypoints: Waypoint[];
  alt: number;
  missionStatus: MissionStatus | null;
  activeFlightId: string | null;
  wsConnected?: boolean;
  selectedWaypointIndex?: number | null;
  onSelectWaypoint?: (index: number) => void;
  lastPacketAgeSec?: number | null;
}) {
  return (
    <>
      <MissionWaypointList
        waypoints={waypoints}
        fallbackAltitude={alt}
        selectedIndex={selectedWaypointIndex}
        onSelect={onSelectWaypoint}
      />

      {missionStatus && (activeFlightId || waypoints.length > 0) && (
        <MissionFlightStatusPanel
          missionStatus={missionStatus}
          wsConnected={wsConnected}
          lastPacketAgeSec={lastPacketAgeSec}
        />
      )}
    </>
  );
}
