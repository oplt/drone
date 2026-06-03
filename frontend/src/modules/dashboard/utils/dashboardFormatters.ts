export const formatNumber = (value: number | null | undefined, suffix = "") => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${value.toLocaleString()}${suffix}`;
};

export const formatDuration = (minutes: number | null | undefined) => {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes))
    return "--";
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return `${h}h ${m}m`;
};

export const formatTime = (iso?: string | null) => {
  if (!iso) return "--";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "--";
  return dt.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
};

export const formatDateLabel = (iso: string) => {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

export const trendFromSeries = (series: number[]) => {
  if (series.length < 2) return "neutral" as const;
  const last = series[series.length - 1];
  const prev = series[series.length - 2];
  if (last > prev) return "up" as const;
  if (last < prev) return "down" as const;
  return "neutral" as const;
};

export const deltaLabelFromSeries = (series: number[]) => {
  if (series.length < 2) return undefined;
  const last = series[series.length - 1];
  const prev = series[series.length - 2];
  if (!Number.isFinite(last) || !Number.isFinite(prev) || prev === 0)
    return undefined;
  const pct = ((last - prev) / Math.abs(prev)) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
};
