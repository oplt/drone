export type HealthState = "healthy" | "degraded" | "down" | "unknown";

export type ObservabilityLinks = {
  grafanaBaseUrl: string | null;
  prometheusUrl: string | null;
  fleetDashboardUrl: string | null;
  apiDashboardUrl: string | null;
  workersDashboardUrl: string | null;
  videoDashboardUrl: string | null;
  mavlinkDashboardUrl: string | null;
  tracesUrl: string | null;
};

export type ServiceStatus = {
  status: HealthState;
  url?: string | null;
};

export type ContextOption = {
  value: string;
  label: string;
};

export type ObservabilityContextOptions = {
  drones: ContextOption[];
  missions: ContextOption[];
};

export type ObservabilityStatus = {
  api: ServiceStatus;
  prometheus: ServiceStatus;
  grafana: ServiceStatus;
  tempo: ServiceStatus;
  telemetry: {
    status: HealthState;
    lagSeconds: number | null;
  };
  workers: {
    status: HealthState;
    queueDepth: number | null;
  };
};
