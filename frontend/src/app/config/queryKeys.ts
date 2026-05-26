export const sessionKeys = {
  all: ["session"] as const,
  currentUser: () => [...sessionKeys.all, "current-user"] as const,
  verified: () => [...sessionKeys.all, "verified"] as const,
};

export const dashboardKeys = {
  all: ["dashboard"] as const,
  analyticsOverview: () => [...dashboardKeys.all, "analytics-overview"] as const,
};

export const missionKeys = {
  all: ["mission-runtime"] as const,
  flightStatus: () => [...missionKeys.all, "flight-status"] as const,
  runtime: (flightId: string) => [...missionKeys.all, "runtime", flightId] as const,
  commandAudit: (flightId: string) => [...missionKeys.all, "command-audit", flightId] as const,
  transitions: (flightId: string) => [...missionKeys.all, "transitions", flightId] as const,
  opsHealth: () => [...missionKeys.all, "ops-health"] as const,
  preflightSettings: () => [...missionKeys.all, "preflight-settings"] as const,
};

export const fieldsKeys = {
  all: ["fields"] as const,
  features: () => [...fieldsKeys.all, "features"] as const,
  geofences: () => [...fieldsKeys.all, "geofences"] as const,
  tileset: (fieldId: number) => [...fieldsKeys.all, "tileset", fieldId] as const,
};

export const planningKeys = {
  all: ["mission-planning"] as const,
  gridPreview: (fingerprint: string) => [...planningKeys.all, "grid", fingerprint] as const,
  patrolPreview: (fingerprint: string) => [...planningKeys.all, "patrol", fingerprint] as const,
};

export const mappingKeys = {
  all: ["mapping-jobs"] as const,
  list: () => [...mappingKeys.all, "list"] as const,
  detail: (jobId: number) => [...mappingKeys.all, "detail", jobId] as const,
};

export const warehouseKeys = {
  all: ["warehouse"] as const,
  maps: () => [...warehouseKeys.all, "maps"] as const,
};

export const videoAnalysisKeys = {
  all: ["video-analysis"] as const,
  job: (jobId: string | null) => [...videoAnalysisKeys.all, "job", jobId] as const,
  detections: (jobId: string | null) => [...videoAnalysisKeys.all, "detections", jobId] as const,
  liveDetections: () => [...videoAnalysisKeys.all, "live-detections"] as const,
};

export const liveObjectDetectionKeys = {
  all: ["live-object-detection"] as const,
  status: () => [...liveObjectDetectionKeys.all, "status"] as const,
};

export const livestockKeys = {
  all: ["livestock"] as const,
  herds: () => [...livestockKeys.all, "herds"] as const,
  positions: (herdId: number) => [...livestockKeys.all, "positions", herdId] as const,
  risk: (herdId: number) => [...livestockKeys.all, "risk", herdId] as const,
};
