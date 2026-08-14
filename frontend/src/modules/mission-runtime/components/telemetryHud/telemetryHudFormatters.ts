export function formatTelemetryHudModelName(path?: string | null): string | null {
  if (!path) return null;
  const base = path.split("/").pop()?.replace(/\.pt$/i, "") ?? path;
  return base.replace(/[-_]/g, "").toUpperCase();
}
