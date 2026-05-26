export type AnalyticsOverview = {
  summary: {
    active_flights: number;
    flights_24h: number;
    telemetry_24h: number;
    flight_hours_7d: number;
    avg_battery_24h: number | null;
  };
  trends: {
    days: string[];
    flight_hours: number[];
    flight_counts: number[];
    telemetry_counts: number[];
  };
  coverage: { label: string; value: number }[];
  recent_flights: {
    id: number;
    name: string;
    status: string;
    started_at: string;
    ended_at: string | null;
    duration_min: number;
    distance_km: number;
    telemetry_points: number;
  }[];
  events: {
    id: number;
    flight_id: number;
    type: string;
    created_at: string;
    data: Record<string, unknown>;
  }[];
  system: {
    telemetry_running: boolean;
    active_connections: number;
    last_update: number;
    mavlink_connected: boolean;
  };
};
