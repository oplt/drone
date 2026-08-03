import {
  Alert,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { previewAgricultureFlight } from "../api";
import type { AgricultureMissionProfile } from "../types";

export function AgriculturePlanPreviewCard({
  fieldId,
  fieldBorder,
  profile,
  cruiseAlt,
  routeLength,
}: {
  fieldId: number | null;
  fieldBorder: [number, number][] | null;
  profile: AgricultureMissionProfile;
  cruiseAlt: number;
  routeLength: number | null;
}) {
  const preview = useQuery({
    queryKey: [
      "agriculture",
      "plan-preview",
      fieldId,
      fieldBorder,
      profile,
      cruiseAlt,
      routeLength,
    ],
    queryFn: () =>
      previewAgricultureFlight({
        field_id: fieldId,
        field_polygon_lonlat: fieldBorder as number[][],
        cruise_alt_m: cruiseAlt,
        route_length_m: routeLength,
        profile,
      }),
    enabled: Boolean(
      fieldBorder && fieldBorder.length >= 3 && Number.isFinite(cruiseAlt),
    ),
    staleTime: 3000,
  });
  if (!fieldBorder || fieldBorder.length < 3)
    return (
      <Alert severity="info">
        Save or draw a field to calculate agriculture footprint and GSD.
      </Alert>
    );
  if (preview.isLoading)
    return (
      <Stack direction="row" spacing={1} alignItems="center">
        <CircularProgress size={16} />
        <Typography variant="caption">Calculating plan preview…</Typography>
      </Stack>
    );
  if (preview.isError)
    return (
      <Alert severity="warning">
        Plan preview unavailable; launch preflight will recheck the profile.
      </Alert>
    );
  const data = preview.data;
  if (!data) return null;
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Typography variant="subtitle2">Agriculture plan preview</Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Chip size="small" label={`${data.area_ha.toFixed(2)} ha`} />
          <Chip
            size="small"
            label={`GSD ${data.estimated_gsd_cm.toFixed(2)} cm`}
          />
          <Chip
            size="small"
            label={`Coverage ${data.coverage_pct.toFixed(0)}%`}
          />
          <Chip
            size="small"
            label={`Images ${data.estimated_image_count ?? "—"}`}
          />
          <Chip
            size="small"
            label={`Duration ${data.estimated_duration_s ? `${Math.ceil(data.estimated_duration_s / 60)} min` : "—"}`}
          />
        </Stack>
        {data.warnings.map((warning) => (
          <Alert key={warning} severity="warning">
            {warning.replaceAll("_", " ")}
          </Alert>
        ))}
      </Stack>
    </Paper>
  );
}
