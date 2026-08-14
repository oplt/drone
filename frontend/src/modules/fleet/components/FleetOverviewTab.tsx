import { Suspense, lazy } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { PageSection } from "../../../shared/layout/PageLayout";
import {
  TelemetryReadout,
  TelemetryReadoutRow,
} from "../../mission-runtime/components/TelemetryReadout";
import type { FleetOverviewSession } from "../hooks/useFleetOverviewSession";
import { FleetPanelSkeleton } from "./FleetPanelSkeleton";

const CustomizedDataGrid = lazy(
  () => import("../../dashboard/components/CustomizedDataGrid"),
);

type FleetOverviewTabProps = {
  session: FleetOverviewSession;
};

export function FleetOverviewTab({ session }: FleetOverviewTabProps) {
  const { data, loading, isConnected, recentRows, derived, linkQuality, batteryPct } = session;

  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, lg: 4 }}>
        <PageSection
          title="System link"
          description="Live link quality, wind exposure, and available battery reserve."
          action={
            <Chip
              size="small"
              label={isConnected ? "Live" : "Offline"}
              color={isConnected ? "success" : "default"}
            />
          }
          sx={{ height: "100%" }}
        >
          <Stack spacing={2}>
            <TelemetryReadoutRow>
              <TelemetryReadout
                label="Battery"
                value={derived.batteryShort}
                warn={batteryPct !== null && batteryPct < 30}
                error={batteryPct !== null && batteryPct < 15}
              />
              <TelemetryReadout label="GPS" value={derived.gpsShort} />
              <TelemetryReadout label="Wind" value={derived.wind} />
              <TelemetryReadout label="Mode" value={derived.modeShort} />
            </TelemetryReadoutRow>
            <Box>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="caption" color="text.secondary">
                  Link quality
                </Typography>
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  {Number.isFinite(linkQuality) ? `${Math.round(linkQuality)}%` : "--"}
                </Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={Number.isFinite(linkQuality) ? linkQuality : 0}
                sx={{ height: 8, borderRadius: 999 }}
              />
            </Box>
            <Typography variant="caption" color="text.secondary">
              Wind {derived.wind} (reported speed, not a quality meter) · {derived.gpsStrength}
            </Typography>
            <Box>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="caption" color="text.secondary">
                  Battery reserve
                </Typography>
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  {batteryPct !== null ? `${Math.round(batteryPct)}%` : "--"}
                </Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={batteryPct ?? 0}
                color={batteryPct !== null && batteryPct < 30 ? "error" : "primary"}
                sx={{ height: 8, borderRadius: 999 }}
              />
            </Box>
          </Stack>
        </PageSection>
      </Grid>
      <Grid size={{ xs: 12, lg: 8 }}>
        <PageSection
          title="Recent flights"
          description="Flight duration, distance, and telemetry density from the latest missions."
          action={<Chip size="small" label={`${data?.recent_flights?.length ?? 0} flights`} />}
        >
          <Suspense fallback={<FleetPanelSkeleton height={520} />}>
            <CustomizedDataGrid rows={recentRows} loading={loading} />
          </Suspense>
        </PageSection>
      </Grid>
    </Grid>
  );
}
