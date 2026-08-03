export type AgricultureMapFeature = {
  geometry?: { type?: string; coordinates?: unknown };
  properties?: Record<string, unknown>;
};

export function indexAgricultureFeatures(features: AgricultureMapFeature[]) {
  return features.map((feature, index) => ({
    feature,
    id: String(feature.properties?.observation_id ?? feature.properties?.id ?? index),
    severity: Number(feature.properties?.severity ?? 0.5),
  }));
}

export function reconnectBackoff(attempt: number, maxMs = 30_000): number {
  const bounded = Math.max(0, Math.min(8, attempt));
  return Math.min(maxMs, 500 * 2 ** bounded);
}
