import { useCallback, useEffect, useState } from "react";
import { getToken } from "../auth";

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
  const apiBaseRaw = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
  const API_BASE = (apiBaseRaw || "http://localhost:8000").replace(/\/$/, "");

  const [data, setData] = useState<TelemetrySummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch_ = useCallback(async () => {
    if (flightId == null) return;
    const token = getToken();
    if (!token) {
      setError("Not authenticated");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE}/analytics/flights/${flightId}/telemetry/summary?resolution=${resolution}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(await res.text());
      setData((await res.json()) as TelemetrySummaryResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load summary");
    } finally {
      setLoading(false);
    }
  }, [API_BASE, flightId, resolution]);

  useEffect(() => {
    setData(null);
    fetch_();
  }, [fetch_]);

  return { data, loading, error, refetch: fetch_ };
}
