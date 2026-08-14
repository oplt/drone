/**
 * Dashboard navigation capabilities derived from existing UserRole values.
 * UI visibility only — backend routes remain authoritative for authorization.
 */

export type DashboardNavCapability =
  | "workspace.overview"
  | "operations.missions"
  | "operations.fleet"
  | "operations.live"
  | "operations.history"
  | "applications.agriculture"
  | "applications.property"
  | "applications.warehouse"
  | "applications.photogrammetry"
  | "applications.animalfarm"
  | "ai.datasets"
  | "ai.video_analysis"
  | "ai.automations"
  | "admin.system"
  | "admin.panel"
  | "settings.account"
  | "settings.workspace";

const ALL_CAPABILITIES: DashboardNavCapability[] = [
  "workspace.overview",
  "operations.missions",
  "operations.fleet",
  "operations.live",
  "operations.history",
  "applications.agriculture",
  "applications.property",
  "applications.warehouse",
  "applications.photogrammetry",
  "applications.animalfarm",
  "ai.datasets",
  "ai.video_analysis",
  "ai.automations",
  "admin.system",
  "admin.panel",
  "settings.account",
  "settings.workspace",
];

const VIEWER_CAPABILITIES: DashboardNavCapability[] = [
  "workspace.overview",
  "operations.fleet",
  "operations.history",
  "applications.agriculture",
  "applications.warehouse",
  "ai.video_analysis",
  "settings.account",
  "settings.workspace",
];

const PILOT_CAPABILITIES: DashboardNavCapability[] = [
  "workspace.overview",
  "operations.missions",
  "operations.fleet",
  "operations.live",
  "operations.history",
  "applications.property",
  "applications.warehouse",
  "applications.photogrammetry",
  "applications.animalfarm",
  "ai.video_analysis",
  "settings.account",
  "settings.workspace",
];

const OPERATOR_CAPABILITIES: DashboardNavCapability[] = [
  ...PILOT_CAPABILITIES,
  "applications.agriculture",
  "ai.automations",
];

const OPS_MANAGER_CAPABILITIES: DashboardNavCapability[] = [
  ...OPERATOR_CAPABILITIES,
  "ai.datasets",
];

const ORG_ADMIN_CAPABILITIES: DashboardNavCapability[] = [
  ...OPS_MANAGER_CAPABILITIES,
  "admin.system",
  "admin.panel",
];

const ROLE_CAPABILITY_MAP: Record<string, DashboardNavCapability[]> = {
  viewer: VIEWER_CAPABILITIES,
  pilot: PILOT_CAPABILITIES,
  operator: OPERATOR_CAPABILITIES,
  ops_manager: OPS_MANAGER_CAPABILITIES,
  org_admin: ORG_ADMIN_CAPABILITIES,
  admin: ALL_CAPABILITIES,
};

export function capabilitiesForRole(role?: string | null): Set<DashboardNavCapability> {
  const normalized = (role ?? "operator").toLowerCase();
  const values = ROLE_CAPABILITY_MAP[normalized] ?? OPERATOR_CAPABILITIES;
  return new Set(values);
}

export function hasNavCapability(
  role: string | null | undefined,
  capability: DashboardNavCapability,
): boolean {
  return capabilitiesForRole(role).has(capability);
}

export function canAccessAdministration(role?: string | null): boolean {
  const caps = capabilitiesForRole(role);
  return caps.has("admin.system") || caps.has("admin.panel");
}
