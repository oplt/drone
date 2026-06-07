export const PREFLIGHT_RUN_POLL_MS = 1500;
export const PREFLIGHT_RUN_POLL_SLOW_MS = 5000;
export const PREFLIGHT_RUN_POLL_BACKOFF_AFTER_MS = 30_000;
export const FLIGHT_READINESS_POLL_MS = 4000;
export const PREFLIGHT_SNAPSHOT_POLL_MS = 5000;
export const PREFLIGHT_SNAPSHOT_STALE_MS = 4000;

export function preflightRunPollIntervalMs(elapsedMs: number): number | false {
  if (elapsedMs < 0) return false;
  if (elapsedMs > PREFLIGHT_RUN_POLL_BACKOFF_AFTER_MS) {
    return PREFLIGHT_RUN_POLL_SLOW_MS;
  }
  return PREFLIGHT_RUN_POLL_MS;
}

export function preflightRunElapsedMs(
  startedAt: string | undefined,
  now = Date.now(),
): number {
  if (!startedAt) return 0;
  const started = Date.parse(startedAt);
  if (!Number.isFinite(started)) return 0;
  return Math.max(0, now - started);
}
