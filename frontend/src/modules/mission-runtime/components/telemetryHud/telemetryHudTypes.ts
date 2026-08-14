export type DetectionHudInfo = {
  enabled: boolean;
  modelName?: string | null;
  fps?: number | null;
  framesProcessed?: number;
  lastError?: string | null;
};

export type TelemetryHudProps = {
  telemetry: unknown;
  cameraTitle?: string;
  missionLabel?: string | null;
  recordingStatus?: string | null;
  detection?: DetectionHudInfo;
  sx?: Record<string, unknown>;
};

export type TelemetryHudMissionPart = {
  text: string;
  emphasis?: boolean;
  dim?: boolean;
};
