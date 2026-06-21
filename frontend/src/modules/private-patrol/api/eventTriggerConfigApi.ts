import { httpRequest } from "../../../shared/api/httpClient";
import type { PatrolAiTask } from "../types";

export type PatrolMqttIntegration = {
  broker: string;
  port: number;
  use_tls: boolean;
  topic: string;
  subscribe_pattern: string;
  auth_hint: string;
  qos: number;
};

export type PatrolSensorIntegration = {
  webhook_url: string;
  auth_hint: string;
  example_body: Record<string, unknown>;
  mqtt?: PatrolMqttIntegration | null;
};

export type PatrolEventTriggerConfig = {
  id: number | null;
  field_id: number;
  field_name?: string | null;
  is_active: boolean;
  enabled: boolean;
  cruise_alt: number;
  speed_mps: number;
  verification_loiter_s: number;
  verification_radius_m: number;
  track_target: boolean;
  target_label?: string | null;
  search_grid_spacing_m: number;
  search_grid_angle_deg: number;
  ai_tasks: string[];
  integration?: PatrolSensorIntegration | null;
};

export function fetchEventTriggerConfig(fieldId: number, token?: string | null) {
  return httpRequest<PatrolEventTriggerConfig>(
    `/api/patrol/event-trigger-config?field_id=${fieldId}`,
    { token },
  );
}

export function saveEventTriggerConfig(
  body: {
    field_id: number;
    enabled?: boolean;
    cruise_alt: number;
    speed_mps: number;
    verification_loiter_s: number;
    verification_radius_m: number;
    track_target: boolean;
    target_label?: string | null;
    search_grid_spacing_m: number;
    search_grid_angle_deg: number;
    ai_tasks: PatrolAiTask[];
  },
  token?: string | null,
) {
  return httpRequest<PatrolEventTriggerConfig>("/api/patrol/event-trigger-config", {
    method: "PUT",
    body,
    token,
  });
}

export function fetchEventTriggerIntegration(token?: string | null) {
  return httpRequest<PatrolSensorIntegration>("/api/patrol/event-trigger-config/integration", {
    token,
  });
}
