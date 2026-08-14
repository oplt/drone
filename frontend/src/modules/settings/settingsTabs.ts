export type SettingsTabKey =
  | "profile"
  | "telemetry"
  | "ai"
  | "credentials"
  | "hardware"
  | "preflight"
  | "alerts"
  | "raspberry"
  | "camera"
  | "photogrammetry";

export const SETTINGS_TAB_INDEX: Record<SettingsTabKey, number> = {
  profile: 0,
  telemetry: 1,
  ai: 2,
  credentials: 3,
  hardware: 4,
  preflight: 5,
  alerts: 6,
  raspberry: 7,
  camera: 8,
  photogrammetry: 9,
};

export const SETTINGS_TAB_LABELS = [
  "Profile",
  "Telemetry",
  "AI",
  "Credentials",
  "Hardware",
  "Preflight Check Params",
  "Alerts",
  "Raspberry",
  "Camera",
  "Photogrammetry",
] as const;
