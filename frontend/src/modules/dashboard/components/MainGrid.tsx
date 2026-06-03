import { Suspense, lazy } from "react";
import Grid from "@mui/material/Grid";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Copyright from "../../session/components/Copyright";
import DashboardAlertsPanel from "./DashboardAlertsPanel";
import DashboardPanelSkeleton from "./DashboardPanelSkeleton";
import DashboardSystemStatus from "./DashboardSystemStatus";
import DashboardTelemetryPanel from "./DashboardTelemetryPanel";
import DashboardTrendCharts from "./DashboardTrendCharts";
import HighlightedCard from "./HighlightedCard";
import StatCard from "./StatCard";
import { useDashboardOverviewModel } from "../hooks/useDashboardOverviewModel";
import PageLayout, { PageSection } from "../../../shared/layout/PageLayout";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";

const ChartUserByCountry = lazy(() => import("./ChartUserByCountry"));
const CustomizedTreeView = lazy(() => import("./CustomizedTreeView"));
const CustomizedDataGrid = lazy(() => import("./CustomizedDataGrid"));

export default function MainGrid() {
  const vm = useDashboardOverviewModel();
  const {
    data,
    loading,
    error,
    refresh,
    activeAlerts,
    alertItems,
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
      description="Monitor field operations, route execution, telemetry health, and coverage trends from one command surface."
      actions={
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25}>
          <Tooltip title="Live websocket telemetry broadcaster state" arrow>
            <Chip
              size="small"
              color={system?.telemetry_running ? "success" : "warning"}
              label={
                system?.telemetry_running
                  ? "Telemetry live"
                  : "Telemetry offline"
              }
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
      hero={<DashboardAlertsPanel items={alertItems} />}
    >
      {error ? <Alert severity="warning">{error}</Alert> : null}

      <Grid container spacing={2} columns={12}>
        {showInitialSkeleton
          ? Array.from({ length: 4 }).map((_, index) => (
              <Grid
                key={`stat-skeleton-${index}`}
                size={{ xs: 12, sm: 6, lg: 3 }}
              >
                <DashboardPanelSkeleton height={190} />
              </Grid>
            ))
          : statCards.map((card) => (
              <Grid key={card.title} size={{ xs: 12, sm: 6, lg: 3 }}>
                <StatCard {...card} />
              </Grid>
            ))}
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          {showInitialSkeleton ? (
            <DashboardPanelSkeleton height={190} />
          ) : (
            <HighlightedCard />
          )}
        </Grid>
      </Grid>

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
            />
          )}
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

      <DashboardTrendCharts
        labels={labels}
        flightHours={trends?.flight_hours}
        flightCounts={trends?.flight_counts}
        telemetryCounts={trends?.telemetry_counts}
        surveyHours7d={summary?.flight_hours_7d}
        flights24h={summary?.flights_24h}
      />

      <Grid container spacing={2} columns={12}>
        <Grid size={{ xs: 12, lg: 9 }}>
          <PageSection
            title="Recent flights"
            description="Mission duration, distance, and telemetry volume across the latest runs."
          >
            <Suspense fallback={<DashboardPanelSkeleton height={500} />}>
              <CustomizedDataGrid rows={recentRows} loading={loading} />
            </Suspense>
          </PageSection>
        </Grid>
        <Grid size={{ xs: 12, lg: 3 }}>
          <Stack gap={2}>
            <Suspense fallback={<DashboardPanelSkeleton height={280} />}>
              <CustomizedTreeView
                summary={summary}
                system={system}
                coverage={data?.coverage}
              />
            </Suspense>
            <DashboardSystemStatus
              telemetryRunning={system?.telemetry_running}
              mavlinkConnected={system?.mavlink_connected}
              activeConnections={system?.active_connections}
              lastUpdateAge={lastUpdateAge}
            />
          </Stack>
        </Grid>
      </Grid>
      <Copyright sx={{ my: 4 }} />
    </PageLayout>
  );
}
