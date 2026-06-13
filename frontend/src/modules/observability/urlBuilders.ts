type GrafanaUrlOptions = {
  droneId?: string | null;
  missionId?: string | null;
  from?: string;
  to?: string;
  orgId?: string | number;
};

export function buildGrafanaUrl(
  baseUrl: string,
  {
    droneId,
    missionId,
    from = "now-1h",
    to = "now",
    orgId = 1,
  }: GrafanaUrlOptions = {},
): string {
  const url = new URL(baseUrl);
  url.searchParams.set("orgId", String(orgId));
  url.searchParams.set("from", from);
  url.searchParams.set("to", to);

  const cleanDroneId = droneId?.trim();
  if (cleanDroneId) {
    url.searchParams.set("var-drone_id", cleanDroneId);
  }

  const cleanMissionId = missionId?.trim();
  if (cleanMissionId) {
    url.searchParams.set("var-mission_id", cleanMissionId);
  }

  return url.toString();
}
