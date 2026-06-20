import { httpRequest } from "../../../shared/api/httpClient";

export type MissionAgentId =
  | "warehouse_scan"
  | "warehouse_inspection"
  | "field_survey"
  | "private_patrol"
  | "property_patrol"
  | "livestock"
  | "mission_planner"
  | "assistant";

export type AgentPhase =
  | "plan"
  | "preflight"
  | "inflight"
  | "postflight"
  | "on_demand"
  | "on_event";

export type AgentResult = {
  agent_id: MissionAgentId;
  phase: AgentPhase;
  output_type: string;
  text: string;
  structured?: Record<string, unknown> | null;
  risk_level?: "low" | "medium" | "high" | "critical" | null;
  requires_human_approval?: boolean;
  profile_id?: string | null;
  model?: string | null;
  latency_ms?: number | null;
  prompt_version?: string;
  status: "ok" | "skipped" | "error";
  error_message?: string | null;
};

export type AgentRunRequest = {
  phase?: AgentPhase;
  question?: string | null;
  mission_runtime_id?: number | null;
  client_flight_id?: string | null;
  mission_type?: string | null;
  warehouse_map_id?: number | null;
  inspection_mission_id?: number | null;
  patrol_incident_id?: number | null;
  property_patrol_incident_id?: number | null;
  livestock_task_id?: number | null;
  structured_payload?: Record<string, unknown>;
};

export type AgentRunOut = {
  id: number;
  agent_id: string;
  phase: string;
  llm_task: string;
  profile_id?: string | null;
  model?: string | null;
  prompt_version: string;
  response_preview?: string | null;
  structured_result?: Record<string, unknown> | null;
  latency_ms?: number | null;
  status: string;
  error_message?: string | null;
  mission_runtime_id?: number | null;
  created_at?: string | null;
};

export async function runMissionAgent(
  agentId: MissionAgentId,
  payload: AgentRunRequest,
): Promise<AgentResult> {
  return httpRequest<AgentResult>(`/api/ai/agents/${agentId}/run`, {
    method: "POST",
    body: payload,
  });
}

export async function listAgentRuns(missionRuntimeId: number): Promise<AgentRunOut[]> {
  return httpRequest<AgentRunOut[]>(
    `/api/ai/agents/runs?mission_runtime_id=${missionRuntimeId}`,
  );
}
