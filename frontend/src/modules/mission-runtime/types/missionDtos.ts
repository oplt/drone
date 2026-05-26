export type MissionLifecycleState =
  | "queued"
  | "running"
  | "paused"
  | "aborted"
  | "completed"
  | "failed";

export type MissionCommand = "pause" | "resume" | "abort";

export type PreflightRunResponse = {
  preflight_run_id: string;
  mission_fingerprint?: string;
  overall_status: string;
  can_start_mission: boolean;
  created_at?: number;
  expires_at?: number;
  report?: {
    mission_type?: string;
    overall_status?: string;
    base_checks?: Array<{
      name: string;
      status: string;
      message?: string | null;
    }>;
    mission_checks?: Array<{
      name: string;
      status: string;
      message?: string | null;
    }>;
    summary?: {
      failed?: number;
      warned?: number;
      passed?: number;
      total_checks?: number;
    };
  };
};

export type MissionRuntimeResponse = {
  flight_id: string;
  mission_name: string;
  mission_type: string;
  state: MissionLifecycleState;
  created_at: number;
  updated_at: number;
  preflight_run_id?: string | null;
  db_flight_id?: string | null;
  last_error?: string | null;
};

export type MissionCreateResponse = {
  flight_id: string;
  status: string;
  mission_name: string;
  mission_type: string;
  waypoints_count: number;
  preflight_run_id?: string | null;
};

export type MissionCommandResponse = {
  flight_id: string;
  command_id: string;
  command: MissionCommand;
  idempotency_key: string;
  state_before: MissionLifecycleState;
  state_after: MissionLifecycleState;
  accepted: boolean;
  message: string;
  requested_at: number;
};

export type MissionCommandAuditResponse = {
  command_id: string;
  command: MissionCommand;
  idempotency_key: string;
  requested_by_user_id: number;
  requested_at: number;
  state_before: MissionLifecycleState;
  state_after: MissionLifecycleState;
  accepted: boolean;
  message: string;
  reason?: string | null;
};

export type MissionStateTransitionResponse = {
  state: string;
  entered_at: number;
  trigger: string;
  command_id?: string | null;
  command?: string | null;
  reason?: string | null;
};
