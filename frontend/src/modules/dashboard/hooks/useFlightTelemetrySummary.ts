import { useCallback, useEffect, useState } from "react";
import { httpRequest } from "../../../shared/api/httpClient";
import { getToken } from "../../session";

export type TelemetryBucket = {
  ts: string;
  avg_alt: number | null;
  min_alt: number | null;
  max_alt: number | null;
  avg_groundspeed: number | null;
  avg_battery_remaining: number | null;
  min_battery_remaining: number | null;
  sample_count: number;
};

export type TelemetrySummaryResponse = {
  flight_id: number;
  resolution_s: number;
  buckets: TelemetryBucket[];
};

export type Resolution = 1 | 10 | 60;

export default function useFlightTelemetrySummary(
  flightId: number | null,
  resolution: Resolution = 10,
) {
  const [data, setData] = useState<TelemetrySummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (flightId == null) {
      setData(null);
      return;
    }
    const token = getToken();
    if (!token) return;

    setLoading(true);
    setError(null);
    try {
      const summary = await httpRequest<TelemetrySummaryResponse>(
        `/telemetry/flights/${flightId}/summary?resolution_s=${resolution}`,
        { token },
      );
      setData(summary);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load telemetry summary");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [flightId, resolution]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, loading, error, refresh: load };
}
