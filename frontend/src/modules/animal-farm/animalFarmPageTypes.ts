export type AnimalFarmWaypoint = { lat: number; lon: number; alt: number };

export type AnimalFarmMissionStatus = {
  flight_id?: string;
  mission_name?: string;
  telemetry?: {
    running: boolean;
    active_connections?: number;
    has_position_data?: boolean;
    position?: {
      lat?: number;
      lon?: number;
      lng?: number;
      alt?: number;
      relative_alt?: number;
    };
  };
  orchestrator?: {
    drone_connected: boolean;
  };
};

export type AnimalFarmPlannedRoute = {
  waypoints: AnimalFarmWaypoint[];
  name: string;
  center: { lat: number; lng: number };
};
