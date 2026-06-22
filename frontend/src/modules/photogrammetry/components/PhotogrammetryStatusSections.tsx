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
}: {
  waypoints: Waypoint[];
  alt: number;
  missionStatus: MissionStatus | null;
  activeFlightId: string | null;
}) {
  return (
    <>
      <MissionWaypointList waypoints={waypoints} fallbackAltitude={alt} />

      {missionStatus && (activeFlightId || waypoints.length > 0) && (
        <MissionFlightStatusPanel missionStatus={missionStatus} />
      )}
    </>
  );
}
