import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { LineChart } from "@mui/x-charts/LineChart";
import useFlightTelemetrySummary, {
  type Resolution,
} from "../../hooks/useFlightTelemetrySummary";

type Props = {
  flightId: number;
  title?: string;
};

const RESOLUTIONS: { label: string; value: Resolution }[] = [
  { label: "1 s", value: 1 },
  { label: "10 s", value: 10 },
  { label: "1 min", value: 60 },
];

function formatTs(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function FlightReplayChart({
  flightId,
  title = `Flight #${flightId} telemetry`,
}: Props) {
  const theme = useTheme();
  const [resolution, setResolution] = useState<Resolution>(10);
  const { data, loading, error } = useFlightTelemetrySummary(
    flightId,
    resolution,
  );

  const buckets = data?.buckets ?? [];

  // Downsample x-axis labels for readability — show at most 12 ticks.
  const labels = useMemo(() => buckets.map((b) => formatTs(b.ts)), [buckets]);
  const tickInterval = useMemo(() => {
    const step = Math.max(1, Math.ceil(buckets.length / 12));
    return (_: unknown, i: number) => i % step === 0;
  }, [buckets.length]);

  const altData = useMemo(
    () => buckets.map((b) => (b.avg_alt != null ? +b.avg_alt.toFixed(1) : null)),
    [buckets],
  );
  const speedData = useMemo(
    () =>
      buckets.map((b) =>
        b.avg_groundspeed != null ? +b.avg_groundspeed.toFixed(2) : null,
      ),
    [buckets],
  );
  const batteryData = useMemo(
    () =>
      buckets.map((b) =>
        b.avg_battery_remaining != null
          ? +b.avg_battery_remaining.toFixed(1)
          : null,
      ),
    [buckets],
  );

  const hasData = buckets.length > 0;

  return (
    <Card variant="outlined" sx={{ width: "100%" }}>
      <CardContent>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          justifyContent="space-between"
          alignItems={{ xs: "flex-start", sm: "center" }}
          spacing={1.5}
          sx={{ mb: 2 }}
        >
          <Stack spacing={0.25}>
            <Typography component="h3" variant="subtitle2">
              {title}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Altitude · groundspeed · battery — aggregated telemetry replay
            </Typography>
          </Stack>

          <Stack direction="row" spacing={1} alignItems="center">
            {loading && <CircularProgress size={16} />}
            <ToggleButtonGroup
              size="small"
              exclusive
              value={resolution}
              onChange={(_, v) => v != null && setResolution(v as Resolution)}
              aria-label="resolution"
            >
              {RESOLUTIONS.map((r) => (
                <ToggleButton key={r.value} value={r.value} sx={{ px: 1.5 }}>
                  {r.label}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
            {hasData && (
              <Chip
                size="small"
                label={`${buckets.length} pts`}
                variant="outlined"
              />
            )}
          </Stack>
        </Stack>

        {error ? (
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        ) : !hasData && !loading ? (
          <Box
            sx={{
              height: 260,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Typography variant="body2" color="text.secondary">
              No telemetry summary available for this flight yet.
            </Typography>
          </Box>
        ) : (
          <LineChart
            // skipAnimation keeps render fast for 1-s resolution (3600+ pts)
            skipAnimation
            xAxis={[
              {
                scaleType: "point",
                data: labels,
                tickInterval,
                height: 28,
              },
            ]}
            yAxis={[
              { id: "alt", label: "Alt (m)", width: 52 },
              { id: "speed", label: "Speed (m/s)", width: 52 },
              { id: "battery", label: "Battery (%)", width: 52, min: 0, max: 100 },
            ]}
            series={[
              {
                id: "alt",
                label: "Altitude (m)",
                data: altData,
                yAxisId: "alt",
                showMark: false,
                curve: "linear",
                color: theme.palette.primary.main,
                connectNulls: false,
              },
              {
                id: "speed",
                label: "Groundspeed (m/s)",
                data: speedData,
                yAxisId: "speed",
                showMark: false,
                curve: "linear",
                color: theme.palette.success.main,
                connectNulls: false,
              },
              {
                id: "battery",
                label: "Battery (%)",
                data: batteryData,
                yAxisId: "battery",
                showMark: false,
                curve: "linear",
                color: theme.palette.warning.main,
                connectNulls: false,
              },
            ]}
            height={280}
            margin={{ left: 0, right: 16, top: 16, bottom: 0 }}
            grid={{ horizontal: true }}
          />
        )}
      </CardContent>
    </Card>
  );
}
