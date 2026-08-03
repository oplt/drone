export type AgricultureEventName =
  | "flight_started"
  | "telemetry_gap"
  | "recording_started"
  | "recording_stopped"
  | "ingest_completed"
  | "quality_completed"
  | "analysis_started"
  | "analysis_progress"
  | "observation_reviewed"
  | "export_ready";

export type AgricultureEvent = {
  type: "agriculture_event";
  name: AgricultureEventName;
  flight_id?: string | null;
  sequence?: number;
  emitted_at?: string;
  payload?: Record<string, unknown>;
};

export function parseAgricultureEvent(value: unknown): AgricultureEvent | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  const names: AgricultureEventName[] = [
    "flight_started",
    "telemetry_gap",
    "recording_started",
    "recording_stopped",
    "ingest_completed",
    "quality_completed",
    "analysis_started",
    "analysis_progress",
    "observation_reviewed",
    "export_ready",
  ];
  return candidate.type === "agriculture_event" &&
    typeof candidate.name === "string" &&
    names.includes(candidate.name as AgricultureEventName)
    ? (candidate as unknown as AgricultureEvent)
    : null;
}
