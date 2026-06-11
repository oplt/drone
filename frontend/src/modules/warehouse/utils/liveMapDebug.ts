export function isLiveMapDebugEnabled(): boolean {
  if (typeof window === "undefined") return false;
  if (!import.meta.env.DEV) return false;
  try {
    return (
      import.meta.env.VITE_LIVE_MAP_DEBUG === "1" ||
      window.localStorage.getItem("live_map_debug") === "1"
    );
  } catch {
    return import.meta.env.VITE_LIVE_MAP_DEBUG === "1";
  }
}

export function liveMapDebugLog(event: string, payload?: Record<string, unknown>): void {
  if (!isLiveMapDebugEnabled()) return;
  if (payload) {
    console.debug(`[live-map] ${event}`, payload);
  } else {
    console.debug(`[live-map] ${event}`);
  }
}
