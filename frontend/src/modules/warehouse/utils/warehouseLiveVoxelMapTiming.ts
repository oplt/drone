const RECONNECT_BASE_MS = 1_500;
const RECONNECT_MAX_MS = 30_000;

export function warehouseLiveMapReconnectDelayMs(
  attempt: number,
  random: () => number = Math.random,
): number {
  const exponent = Math.max(0, Math.floor(attempt) - 1);
  const cappedDelay = Math.min(
    RECONNECT_MAX_MS,
    RECONNECT_BASE_MS * 2 ** exponent,
  );
  const jitter = 0.8 + Math.min(1, Math.max(0, random())) * 0.2;
  return Math.round(cappedDelay * jitter);
}

export function warehouseLiveMapSnapshotPollDelayMs(
  attempt: number,
  random: () => number = Math.random,
): number {
  return warehouseLiveMapReconnectDelayMs(attempt, random);
}
