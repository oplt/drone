import { useEffect, useState } from "react";
import { Box, Stack, Typography } from "@mui/material";
import { fetchWarehouseScannedMapQuality } from "../api/warehouseMissionsApi";
import type { WarehouseScannedMapQualityResponse } from "../types/missions";

type Props = {
  jobId: number | null;
  getToken: () => string | null;
  onError: (message: string) => void;
};

export function WarehouseMapQualityPanel({ jobId, getToken, onError }: Props) {
  const [quality, setQuality] = useState<WarehouseScannedMapQualityResponse | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token || jobId == null) {
      return;
    }
    let cancelled = false;
    fetchWarehouseScannedMapQuality(jobId, token)
      .then((next) => {
        if (!cancelled) setQuality(next);
      })
      .catch((error) => {
        if (!cancelled) onError(`Map quality could not be loaded: ${error}`);
      });
    return () => {
      cancelled = true;
    };
  }, [getToken, jobId, onError]);

  if (jobId == null || !quality) return null;

  return (
    <Box sx={{ p: 1.25, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
      <Stack direction="row" spacing={1.5} flexWrap="wrap">
        <Metric label="Source" value={quality.source} />
        <Metric label="Quality" value={formatValue(quality.quality_score, "")} />
        <Metric label="Rating" value={qualityRating(quality)} />
        <Metric label="Coverage" value={formatValue(quality.coverage_percent, "%")} />
        <Metric label="Drift" value={formatValue(quality.drift_estimate_m, "m")} />
      </Stack>
    </Box>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Box>
  );
}

function formatValue(value: number | null | undefined, unit: string): string {
  if (typeof value !== "number") return "--";
  return `${value.toFixed(value >= 10 ? 0 : 2)}${unit ? ` ${unit}` : ""}`;
}

function qualityRating(quality: WarehouseScannedMapQualityResponse): string {
  const coverage = quality.coverage_percent ?? 0;
  const drift = quality.drift_estimate_m ?? Number.POSITIVE_INFINITY;
  const score = quality.quality_score ?? 0;
  if (coverage >= 80 && drift <= 0.5 && score >= 0.75) return "Good map";
  if (coverage >= 60 && drift <= 1.0) return "Acceptable";
  if (coverage > 0 || Number.isFinite(drift)) return "Needs rescan";
  return "--";
}
