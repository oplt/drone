import type { MissionCommand, MissionLifecycleState, PreflightRunResponse } from "./missionDtos";

export type OpsQueueSnapshot = {
  depth: number;
  capacity: number;
  utilization_pct: number;
};

export type OpsHealthResponse = {
  status: "healthy" | "degraded" | "offline";
  generated_at: number;
  telemetry: {
    running: boolean;
    source_connected: boolean;
    active_connections: number;
    last_update: number;
    last_update_age_sec?: number | null;
    has_recent_update: boolean;
    recent_threshold_sec: number;
  };
  video: {
    available: boolean;
    healthy?: boolean;
    frame_count?: number;
    fps?: number;
    resolution?: string;
    recording?: boolean;
    recording_file?: string | null;
    error?: string;
  };
  queues: {
    db_event: OpsQueueSnapshot;
    db_lifecycle: OpsQueueSnapshot;
    raw_event: OpsQueueSnapshot;
  };
  runtime_metrics: Record<string, unknown>;
  shadow: {
    shadow_mode_active: boolean;
    old_path: {
      writes_attempted: number;
      writes_ok: number;
      writes_failed: number;
      error_rate_pct: number;
    };
    new_path: {
      events_enqueued: number;
      dropped_db_events: number;
      worker_batches_completed: number;
    };
    interpretation: string;
  };
  active_mission?: {
    flight_id: string;
    mission_name: string;
    mission_type: string;
    state: string;
    updated_at?: number | null;
  } | null;
  alerts: string[];
};

export type TelemetrySnapshot = Record<string, unknown>;

export type MissionLifecycleEvent = {
  type: "mission_lifecycle";
  data?: {
    mission?: { client_flight_id?: string | null };
    mission_runtime_id?: string | null;
    emitted_at?: string;
    payload?: { state?: string };
  };
};

export type TelemetrySocketMessage =
  | MissionLifecycleEvent
  | { type: "telemetry"; data?: TelemetrySnapshot }
  | { type: "pong" }
  | Record<string, unknown>;

export type MissionLifecycleSlice = {
  flight_id?: string | null;
  state?: MissionLifecycleState;
  mission_name?: string;
  mission_type?: string;
  updated_at?: number;
  last_error?: string | null;
};

export type MissionStatusPayload = {
  flight_id?: string;
  mission_name?: string;
  mission_lifecycle?: MissionLifecycleSlice | null;
  command_capabilities?: {
    pause?: boolean;
    resume?: boolean;
    abort?: boolean;
  } | null;
  orchestrator?: { drone_connected?: boolean };
  telemetry?: { running?: boolean };
};

export type RuntimeConnectionState = "connecting" | "online" | "degraded" | "offline";

export type MissionRuntimeFacade<TStatus extends MissionStatusPayload = MissionStatusPayload> = {
  missionStatus: TStatus | null;
  activeFlightId: string | null;
  setPendingFlightId: (flightId: string | null) => void;
  telemetry: TelemetrySnapshot | null;
  connection: RuntimeConnectionState;
  wsConnected: boolean;
  droneConnected: boolean;
  telemetryError: string | null;
  reconnect: () => void;
  disconnect: () => void;
};

export type VideoStreamState = {
  starting: boolean;
  streamKey: number;
  error: string | null;
};

export type PreflightState = {
  run: PreflightRunResponse | null;
  canStart: boolean;
  overallStatus: string;
};

export type MissionCommandActions = {
  issueCommand: (command: MissionCommand) => Promise<void>;
  busyCommand: MissionCommand | null;
  message: string | null;
  error: string | null;
  capabilities: { pause: boolean; resume: boolean; abort: boolean };
};
