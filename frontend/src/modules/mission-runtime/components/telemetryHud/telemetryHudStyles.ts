export const TELEMETRY_HUD_MONO =
  '"Roboto Mono", "SFMono-Regular", Consolas, monospace';

export const TELEMETRY_HUD_GLASS = {
  bgcolor: "rgba(0, 0, 0, 0.38)",
  backdropFilter: "blur(10px)",
  WebkitBackdropFilter: "blur(10px)",
  border: "1px solid rgba(255, 255, 255, 0.1)",
  borderRadius: 2,
  boxShadow: "0 2px 12px rgba(0, 0, 0, 0.25)",
} as const;

export function telemetryHudValueColor(warn?: boolean, error?: boolean) {
  if (error) return "error.light";
  if (warn) return "warning.light";
  return "common.white";
}
