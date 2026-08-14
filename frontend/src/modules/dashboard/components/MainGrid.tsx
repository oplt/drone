import { Suspense, lazy, useState } from "react";
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router-dom";
import Copyright from "../../session/components/Copyright";
import DashboardAlertsPanel from "./DashboardAlertsPanel";
import DashboardPanelSkeleton from "./DashboardPanelSkeleton";
import DashboardSystemStatus from "./DashboardSystemStatus";
import DashboardTelemetryPanel from "./DashboardTelemetryPanel";
import DashboardTrendCharts from "./DashboardTrendCharts";
import StatCard from "./StatCard";
import { useDashboardOverviewModel } from "../hooks/useDashboardOverviewModel";
import { useTelemetryLinkStatus } from "../../mission-runtime";
import PageLayout, { PageSection } from "../../../shared/layout/PageLayout";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { FeatureState } from "../../../shared/ui";

const ChartUserByCountry = lazy(() => import("./ChartUserByCountry"));
const CustomizedTreeView = lazy(() => import("./CustomizedTreeView"));
const CustomizedDataGrid = lazy(() => import("./CustomizedDataGrid"));

export default function MainGrid() {
  const vm = useDashboardOverviewModel();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const linkStatus = useTelemetryLinkStatus({
    enabled: Boolean(vm.system?.mavlink_connected),
  });
  const {
    data,
    loading,
    error,
    refresh,
    activeAlerts,
    alertItems,
    alertsLoadError,
    refreshAlerts,
    system,
    summary,
    trends,
    labels,
    statCards,
    recentRows,
    showInitialSkeleton,
    lastUpdateAge,
    telemetry,
  } = vm;

  return (
    <PageLayout
      eyebrow="Operations pulse"
      title="Live command overview"
      description="Needs attention first, then live vehicle health, then historical trends."
      actions={
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25}>
          <Tooltip title={linkStatus.label} arrow>
            <Chip
              size="small"
              color={linkStatus.color}
              label={linkStatus.label}
              variant={linkStatus.phase === "live" ? "filled" : "outlined"}
            />
          </Tooltip>
          <Tooltip title="Vehicle transport link state" arrow>
            <Chip
              size="small"
              color={system?.mavlink_connected ? "success" : "default"}
              label={
                system?.mavlink_connected ? "MAVLink connected" : "MAVLink idle"
              }
            />
          </Tooltip>
          <ActionIconButton
            variant="refresh"
            title="Refresh data"
            onClick={refresh}
          />
        </Stack>
      }
      metrics={[
        {
          label: "Open alerts",
          value: `${activeAlerts.length || alertItems.length}`,
          caption: activeAlerts.length > 0 ? "Review" : "Nominal",
          tooltip:
            "Active operational alerts from alert center and telemetry fallback checks.",
        },
        {
          label: "Live clients",
          value: `${system?.active_connections ?? 0}`,
          caption: "Operators",
          tooltip: "Number of connected dashboard/operator sessions.",
        },
        {
          label: "Last telemetry",
          value: lastUpdateAge !== null ? `${lastUpdateAge}s` : "--",
          caption: "Heartbeat",
          tooltip: "Elapsed time since latest telemetry update.",
        },
      ]}
      hero={
        <DashboardAlertsPanel
          items={alertItems}
          loadError={alertsLoadError}
          onRetryLoad={() => void refreshAlerts()}
        />
      }
    >
      {/* Zone 1: needs attention = hero alerts. Zone 2: live vehicle + link. */}
      <Grid container spacing={2} columns={12}>
        <Grid size={{ xs: 12, lg: 8 }}>
          {showInitialSkeleton ? (
            <DashboardPanelSkeleton height={260} />
          ) : (
            <DashboardTelemetryPanel
              isConnected={telemetry.isConnected}
              mode={telemetry.mode}
              altitudeM={telemetry.altitudeM}
              speedMps={telemetry.speedMps}
              batteryPct={telemetry.batteryPct}
              satellites={telemetry.satellites}
              hdop={telemetry.hdop}
              gpsQualityScore={telemetry.gpsQualityScore}
              gpsStrength={telemetry.gpsStrength}
              batteryShort={telemetry.batteryShort}
              gpsShort={telemetry.gpsShort}
              speedShort={telemetry.speedShort}
              altShort={telemetry.altShort}
              modeShort={telemetry.modeShort}
            />
          )}
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Stack gap={2}>
            <DashboardSystemStatus
              telemetryRunning={system?.telemetry_running}
              mavlinkConnected={system?.mavlink_connected}
              activeConnections={system?.active_connections}
              lastUpdateAge={lastUpdateAge}
            />
            <PageSection
              title="System details"
              description="Expanded coverage and service map for diagnostics."
              action={
                <Button
                  size="small"
                  onClick={() => setDetailsOpen((open) => !open)}
                  aria-expanded={detailsOpen}
                >
                  {detailsOpen ? "Hide details" : "Show details"}
                </Button>
              }
            >
              {!detailsOpen ? (
                <Stack spacing={1}>
                  <Chip
                    size="small"
                    variant="outlined"
                    label="Details collapsed"
                    sx={{ alignSelf: "flex-start" }}
                  />
                  <Typography variant="body2" color="text.secondary">
                    Expand for field ops tree, telemetry counters, and coverage
                    segments.
                  </Typography>
                </Stack>
              ) : null}
              <Collapse in={detailsOpen} unmountOnExit>
                <Suspense fallback={<DashboardPanelSkeleton height={280} />}>
                  <CustomizedTreeView
                    summary={summary}
                    system={system}
                    coverage={data?.coverage}
                  />
                </Suspense>
              </Collapse>
            </PageSection>
          </Stack>
        </Grid>
      </Grid>

      {/* Zone 3: trends / history — below fold */}
      <FeatureState error={error} onRetry={refresh} stale={Boolean(error && data)}>
        {showInitialSkeleton ? (
          <Grid container spacing={2} columns={12}>
            {Array.from({ length: 4 }).map((_, index) => (
              <Grid
                key={`stat-skeleton-${index}`}
                size={{ xs: 12, sm: 6, lg: 3 }}
              >
                <DashboardPanelSkeleton height={190} />
              </Grid>
            ))}
          </Grid>
        ) : (
          <>
            <Grid container spacing={2} columns={12}>
              {statCards.map((card) => (
                <Grid key={card.title} size={{ xs: 12, sm: 6, lg: 3 }}>
                  <StatCard {...card} />
                </Grid>
              ))}
            </Grid>

            <DashboardTrendCharts
              labels={labels}
              flightHours={trends?.flight_hours}
              flightCounts={trends?.flight_counts}
              telemetryCounts={trends?.telemetry_counts}
              surveyHours7d={summary?.flight_hours_7d}
              flights24h={summary?.flights_24h}
            />

            <Grid container spacing={2} columns={12}>
              <Grid size={{ xs: 12, lg: 8 }}>
                <PageSection
                  title="Recent flights"
                  description="Mission duration, distance, and telemetry volume across the latest runs."
                >
                  {!loading && recentRows.length === 0 ? (
                    <FeatureState
                      empty={{
                        title: "No recent flights",
                        description:
                          "Completed and active missions will list here. Start from Fleet or Controlled Flight.",
                        action: (
                          <Stack direction="row" spacing={1}>
                            <Button
                              component={RouterLink}
                              to="/dashboard/fleet"
                              variant="contained"
                              size="small"
                            >
                              Open Fleet
                            </Button>
                            <Button
                              component={RouterLink}
                              to="/dashboard/controlled"
                              variant="outlined"
                              size="small"
                            >
                              Controlled Flight
                            </Button>
                          </Stack>
                        ),
                      }}
                    >
                      {null}
                    </FeatureState>
                  ) : (
                    <Suspense fallback={<DashboardPanelSkeleton height={500} />}>
                      <CustomizedDataGrid rows={recentRows} loading={loading} />
                    </Suspense>
                  )}
                </PageSection>
              </Grid>
              <Grid size={{ xs: 12, lg: 4 }}>
                <Suspense fallback={<DashboardPanelSkeleton height={390} />}>
                  <ChartUserByCountry
                    segments={data?.coverage}
                    totalLabel="Flight coverage"
                  />
                </Suspense>
              </Grid>
            </Grid>
          </>
        )}
      </FeatureState>
      <Copyright sx={{ my: 4 }} />
    </PageLayout>
  );
}
