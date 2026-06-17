import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Grid from "@mui/material/Grid";
import MenuItem from "@mui/material/MenuItem";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ApiRoundedIcon from "@mui/icons-material/ApiRounded";
import BugReportRoundedIcon from "@mui/icons-material/BugReportRounded";
import CloudQueueRoundedIcon from "@mui/icons-material/CloudQueueRounded";
import DirectionsRoundedIcon from "@mui/icons-material/DirectionsRounded";
import HubRoundedIcon from "@mui/icons-material/HubRounded";
import MemoryRoundedIcon from "@mui/icons-material/MemoryRounded";
import QueryStatsRoundedIcon from "@mui/icons-material/QueryStatsRounded";
import TimelineRoundedIcon from "@mui/icons-material/TimelineRounded";
import VideocamRoundedIcon from "@mui/icons-material/VideocamRounded";
import { useSearchParams } from "react-router-dom";
import { dashboardKeys } from "../../app/config/queryKeys";
import Header from "../../shared/layout/WorkflowHeader";
import PageLayout, { PageSection } from "../../shared/layout/PageLayout";
import { useCurrentUser } from "../session";
import {
  fetchObservabilityContextOptions,
  fetchObservabilityLinks,
  fetchObservabilityStatus,
} from "./api";
import HealthStatusCard, { titleCaseStatus } from "./components/HealthStatusCard";
import HealthStatusGrid from "./components/HealthStatusGrid";
import ObservabilityShortcutCard from "./components/ObservabilityShortcutCard";
import ObservabilityShortcutGrid, {
  SHORTCUTS_PER_ROW,
} from "./components/ObservabilityShortcutGrid";
import type { ObservabilityLinks } from "./types";
import { buildGrafanaUrl } from "./urlBuilders";

const TIME_RANGES = [
  { label: "Last hour", from: "now-1h", to: "now" },
  { label: "Last 6 hours", from: "now-6h", to: "now" },
  { label: "Last 24 hours", from: "now-24h", to: "now" },
  { label: "Last 7 days", from: "now-7d", to: "now" },
];

function isAdminLike(role?: string | null) {
  return role === "admin" || role === "developer";
}

function canInvestigate(role?: string | null) {
  return ["admin", "developer", "org_admin", "ops_manager", "pilot", "operator"].includes(
    role ?? "",
  );
}

function contextUrl(
  url: string | null | undefined,
  filters: { droneId: string; missionId: string; from: string; to: string },
) {
  if (!url) return null;
  return buildGrafanaUrl(url, {
    droneId: filters.droneId,
    missionId: filters.missionId,
    from: filters.from,
    to: filters.to,
    orgId: 1,
  });
}

const COMPACT_SECTION_SX = {
  p: { xs: 2, md: 2.25 },
  "& > .MuiStack-root:first-of-type": { mb: 1.5 },
} as const;

export default function ObservabilityPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useCurrentUser();
  const [droneId, setDroneId] = useState(searchParams.get("drone_id") ?? "");
  const [missionId, setMissionId] = useState(searchParams.get("mission_id") ?? "");
  const [range, setRange] = useState(TIME_RANGES[0]);

  const linksQuery = useQuery({
    queryKey: dashboardKeys.observabilityLinks(),
    queryFn: ({ signal }) => fetchObservabilityLinks(signal),
  });
  const statusQuery = useQuery({
    queryKey: dashboardKeys.observabilityStatus(),
    queryFn: ({ signal }) => fetchObservabilityStatus(signal),
    refetchInterval: 30_000,
  });
  const contextOptionsQuery = useQuery({
    queryKey: dashboardKeys.observabilityContextOptions(),
    queryFn: ({ signal }) => fetchObservabilityContextOptions(signal),
  });

  const droneOptions = contextOptionsQuery.data?.drones ?? [];
  const missionOptions = contextOptionsQuery.data?.missions ?? [];
  const droneValues = useMemo(() => droneOptions.map((item) => item.value), [droneOptions]);
  const missionValues = useMemo(
    () => missionOptions.map((item) => item.value),
    [missionOptions],
  );
  const droneLabels = useMemo(
    () => new Map(droneOptions.map((item) => [item.value, item.label])),
    [droneOptions],
  );
  const missionLabels = useMemo(
    () => new Map(missionOptions.map((item) => [item.value, item.label])),
    [missionOptions],
  );

  const filters = useMemo(
    () => ({ droneId, missionId, from: range.from, to: range.to }),
    [droneId, missionId, range],
  );

  const links: Partial<ObservabilityLinks> = linksQuery.data ?? {};
  const role = user?.role;
  const health = statusQuery.data;

  const shortcuts = [
    {
      title: "Fleet Health",
      description: "Drone connectivity, telemetry freshness, battery, mission status.",
      buttonLabel: "Open dashboard",
      url: contextUrl(links.fleetDashboardUrl, filters),
      icon: <HubRoundedIcon />,
      visible: true,
    },
    {
      title: "Current Drone",
      description: "Focused dashboard for the selected drone and current operating window.",
      buttonLabel: "Open drone view",
      url: contextUrl(links.fleetDashboardUrl, filters),
      icon: <DirectionsRoundedIcon />,
      visible: true,
    },
    {
      title: "Mission Timeline",
      description: "Mission events, command latency, telemetry gaps, and operator actions.",
      buttonLabel: "Open timeline",
      url: contextUrl(links.fleetDashboardUrl, filters),
      icon: <TimelineRoundedIcon />,
      visible: true,
    },
    {
      title: "Backend API",
      description: "Latency, error rate, request volume, saturation.",
      buttonLabel: "Open dashboard",
      url: contextUrl(links.apiDashboardUrl, filters),
      icon: <ApiRoundedIcon />,
      visible: true,
    },
    {
      title: "Workers / Celery",
      description: "Queue depth, task duration, retries, failed jobs.",
      buttonLabel: "Open dashboard",
      url: contextUrl(links.workersDashboardUrl, filters),
      icon: <CloudQueueRoundedIcon />,
      visible: true,
    },
    {
      title: "Video AI Pipeline",
      description: "Frame processing latency, dropped frames, model inference time.",
      buttonLabel: "Open dashboard",
      url: contextUrl(links.videoDashboardUrl, filters),
      icon: <VideocamRoundedIcon />,
      visible: true,
    },
    {
      title: "MAVLink / Telemetry",
      description: "Heartbeat, message rate, command ACK latency, disconnects.",
      buttonLabel: "Open dashboard",
      url: contextUrl(links.mavlinkDashboardUrl, filters),
      icon: <MemoryRoundedIcon />,
      visible: true,
    },
    {
      title: "Tempo Traces",
      description: "Investigate slow requests, mission commands, dispatch failures.",
      buttonLabel: "Open Explore",
      url: contextUrl(links.tracesUrl, filters),
      icon: <QueryStatsRoundedIcon />,
      visible: canInvestigate(role),
    },
    {
      title: "Prometheus Debug",
      description: "Raw PromQL query UI. Developer/admin use only.",
      buttonLabel: "Open Prometheus",
      url: links.prometheusUrl ?? null,
      icon: <BugReportRoundedIcon />,
      restricted: true,
      visible: isAdminLike(role),
    },
  ];

  const updateContextParam = (key: "drone_id" | "mission_id", value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value.trim()) next.set(key, value.trim());
    else next.delete(key);
    setSearchParams(next, { replace: true });
  };

  const openExternal = (url: string) => {
    window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <>
      <Header />
      <PageLayout
        title="Observability"
      >
        <Stack spacing={1.5}>
          {linksQuery.error ? (
            <Alert severity="warning">Observability links are unavailable right now.</Alert>
          ) : null}

          <PageSection
            sx={COMPACT_SECTION_SX}
            description="Dashboard links include the selected drone, mission, and time range when configured."
          >
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 4 }}>
              <Autocomplete
                freeSolo
                fullWidth
                options={droneValues}
                loading={contextOptionsQuery.isLoading}
                value={droneId}
                getOptionLabel={(option) => droneLabels.get(option) ?? option}
                onChange={(_event, value) => {
                  const next = (value ?? "").toString();
                  setDroneId(next);
                  updateContextParam("drone_id", next);
                }}
                onInputChange={(_event, value, reason) => {
                  if (reason === "input") setDroneId(value);
                }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Drone ID"
                    placeholder="Select or type a drone"
                    helperText="Drones registered in fleet readiness"
                    onBlur={() => updateContextParam("drone_id", droneId)}
                  />
                )}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 4 }}>
              <Autocomplete
                freeSolo
                fullWidth
                options={missionValues}
                loading={contextOptionsQuery.isLoading}
                value={missionId}
                getOptionLabel={(option) => missionLabels.get(option) ?? option}
                onChange={(_event, value) => {
                  const next = (value ?? "").toString();
                  setMissionId(next);
                  updateContextParam("mission_id", next);
                }}
                onInputChange={(_event, value, reason) => {
                  if (reason === "input") setMissionId(value);
                }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Mission ID"
                    placeholder="Select or type a mission"
                    helperText="Recent missions from the database"
                    onBlur={() => updateContextParam("mission_id", missionId)}
                  />
                )}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 4 }}>
              <TextField
                select
                fullWidth
                label="Time range"
                value={range.label}
                onChange={(event) => {
                  const next = TIME_RANGES.find((item) => item.label === event.target.value);
                  if (next) setRange(next);
                }}
              >
                {TIME_RANGES.map((item) => (
                  <MenuItem key={item.label} value={item.label}>
                    {item.label}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
          </Grid>
          </PageSection>

          <PageSection title="System health" sx={COMPACT_SECTION_SX}>
            <HealthStatusGrid>
            <HealthStatusCard
              title="API Status"
              value={titleCaseStatus(health?.api.status ?? "unknown")}
              status={health?.api.status ?? "unknown"}
              loading={statusQuery.isLoading}
            />
            <HealthStatusCard
              title="Telemetry Lag"
              value={
                health?.telemetry.lagSeconds == null
                  ? "Unknown"
                  : `${health.telemetry.lagSeconds.toFixed(0)}s`
              }
              status={health?.telemetry.status ?? "unknown"}
              loading={statusQuery.isLoading}
            />
            <HealthStatusCard
              title="Prometheus"
              value={titleCaseStatus(health?.prometheus.status ?? "unknown")}
              status={health?.prometheus.status ?? "unknown"}
              caption={health?.prometheus.url ?? links.prometheusUrl ?? undefined}
              href={health?.prometheus.url ?? links.prometheusUrl}
              loading={statusQuery.isLoading}
            />
            <HealthStatusCard
              title="Grafana"
              value={titleCaseStatus(health?.grafana.status ?? "unknown")}
              status={health?.grafana.status ?? "unknown"}
              caption={health?.grafana.url ?? links.grafanaBaseUrl ?? undefined}
              href={health?.grafana.url ?? links.grafanaBaseUrl}
              loading={statusQuery.isLoading}
            />
            <HealthStatusCard
              title="Tempo"
              value={titleCaseStatus(health?.tempo.status ?? "unknown")}
              status={health?.tempo.status ?? "unknown"}
              caption={health?.tempo.url ?? links.tracesUrl ?? undefined}
              href={health?.tempo.url ?? links.tracesUrl}
              loading={statusQuery.isLoading}
            />
            <HealthStatusCard title="Active Drones" value="Unknown" status="unknown" />
            <HealthStatusCard title="Running Missions" value="Unknown" status="unknown" />
            <HealthStatusCard
              title="Worker Queue"
              value={
                health?.workers.queueDepth == null ? "Unknown" : String(health.workers.queueDepth)
              }
              status={health?.workers.status ?? "unknown"}
              loading={statusQuery.isLoading}
            />
            <HealthStatusCard title="Failed Commands" value="Unknown" status="unknown" />
            </HealthStatusGrid>
          </PageSection>

          <PageSection
            sx={COMPACT_SECTION_SX}
            title="Investigation shortcuts"
            description="Grafana is the main investigation UI. Prometheus remains a restricted debug tool."
          >
          {linksQuery.isLoading ? (
            <ObservabilityShortcutGrid>
              {Array.from({ length: SHORTCUTS_PER_ROW }).map((_, index) => (
                <Skeleton
                  key={index}
                  variant="rectangular"
                  height={148}
                  sx={{ borderRight: "1px solid", borderBottom: "1px solid", borderColor: "divider" }}
                />
              ))}
            </ObservabilityShortcutGrid>
          ) : (
            <ObservabilityShortcutGrid>
              {shortcuts
                .filter((shortcut) => shortcut.visible)
                .map((shortcut) => (
                  <ObservabilityShortcutCard key={shortcut.title} {...shortcut} onOpen={openExternal} />
                ))}
            </ObservabilityShortcutGrid>
          )}
          </PageSection>
        </Stack>
      </PageLayout>
    </>
  );
}
