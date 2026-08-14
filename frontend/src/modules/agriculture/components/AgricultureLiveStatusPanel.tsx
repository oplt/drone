import {
  Alert,
  Button,
  Chip,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import { useState } from "react";
import {
  useAgricultureAnalysisRuns,
  useAgricultureAnalysisReadiness,
  useAgricultureFlight,
  useAgricultureFlightCoverage,
  useAgricultureFlightQuality,
  useAgricultureAnalysisQuality,
  useAgricultureRuntimeEvents,
  useCreateAgricultureAnalysisRun,
  useProcessAgricultureAnalysisRun,
} from "../hooks";
import type { AgricultureEvent } from "../runtime";
import { AnalysisRunProgress } from "./AnalysisRunProgress";
import { FlightQualityPanel } from "./FlightQualityPanel";
import { AgricultureAccessibilityBoundary } from "./AgricultureAccessibilityBoundary";
import { AgricultureMediaInventoryPanel } from "./AgricultureMediaInventoryPanel";
import { AgricultureUploadPanel } from "./AgricultureUploadPanel";
import { MissionCommandPanel } from "../../mission-runtime/components/MissionCommandPanel";
import { useMissionRuntime } from "../../mission-runtime/hooks/useMissionRuntime";
import { AgricultureLiveControls } from "./AgricultureLiveControls";
import { AgricultureLiveMap } from "./AgricultureLiveMap";
import { useBrowserOnline } from "../hooks/useBrowserOnline";
import { AgricultureCapabilitySelector } from "./AgricultureCapabilitySelector";
import { AgricultureJourneyStepper } from "./AgricultureJourneyStepper";
import { FeatureState } from "../../../shared/ui/FeatureState";

type LiveStage = "live" | "media" | "analysis";

export function AgricultureLiveStatusPanel({
  flightId,
  active,
  event,
  sequenceGap,
}: {
  flightId: string | null;
  active: boolean;
  event?: AgricultureEvent | null;
  sequenceGap?: boolean;
}) {
  const flight = useAgricultureFlight(flightId, active);
  const quality = useAgricultureFlightQuality(flightId, active);
  const coverage = useAgricultureFlightCoverage(flightId, active);
  const runs = useAgricultureAnalysisRuns(flightId);
  const readiness = useAgricultureAnalysisReadiness(flightId, !active);
  const [capabilitySelection, setCapabilitySelection] = useState<{
    flightId: string;
    values: string[];
  } | null>(null);
  const [createdRun, setCreatedRun] = useState<{
    flightId: string;
    runId: string;
  } | null>(null);
  const [stage, setStage] = useState<LiveStage>("live");
  const createRun = useCreateAgricultureAnalysisRun();
  const processRun = useProcessAgricultureAnalysisRun();
  const runtime = useMissionRuntime({ onError: () => undefined, alwaysConnect: active });
  const browserOnline = useBrowserOnline();
  const recoveredRuntimeEvents = useAgricultureRuntimeEvents(flightId, active);
  const availableCapabilityIds = new Set(
    readiness.data?.capabilities
      .filter((capability) => capability.available)
      .map((capability) => capability.id) ?? [],
  );
  const selectedCapabilities =
    capabilitySelection &&
    capabilitySelection.flightId === readiness.data?.flight_id
      ? capabilitySelection.values.filter((capability) =>
          availableCapabilityIds.has(capability),
        )
      : readiness.data?.capabilities
          .filter((capability) => capability.available && capability.recommended)
          .map((capability) => capability.id) ?? [];
  const runId =
    runs.data?.[0]?.id ??
    (createdRun?.flightId === flightId ? createdRun.runId : null);
  const analysisQuality = useAgricultureAnalysisQuality(runId);
  if (!flightId)
    return (
      <FeatureState
        empty={{
          title: "No active agriculture flight",
          description: "Save field, configure agriculture profile, then start flight.",
        }}
      >
        {null}
      </FeatureState>
    );
  if (flight.isLoading)
    return <FeatureState loading>{null}</FeatureState>;
  if (flight.isError && !flight.data)
    return (
      <FeatureState
        error="Agriculture flight state unavailable. Live telemetry remains active; polling will retry."
        onRetry={() => void flight.refetch()}
      >
        {null}
      </FeatureState>
    );
  const q = (quality.data?.quality ?? {}) as Record<string, unknown>;
  const c = (coverage.data?.coverage ?? {}) as Record<string, unknown>;
  const startPostFlight = async () => {
    if (!flightId) return;
    const run = await createRun.mutateAsync({
      flightId,
      requestedAnalyses: selectedCapabilities,
    });
    setCreatedRun({ flightId, runId: run.id });
    await processRun.mutateAsync(run.id);
  };
  return (
    <AgricultureAccessibilityBoundary component="div">
      <Stack
        component="section"
        aria-labelledby="agriculture-flight-status-heading"
        spacing={1}
        sx={{ mt: 2, p: 2, bgcolor: "background.paper", borderRadius: 1 }}
      >
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          flexWrap="wrap"
          useFlexGap
        >
          <Typography
            id="agriculture-flight-status-heading"
            variant="subtitle2"
          >
            Agriculture flight
          </Typography>
          <Chip
            size="small"
            label={String(flight.data?.status ?? "unknown")}
            color={active ? "success" : "default"}
          />
          <Chip
            size="small"
            variant="outlined"
            label={`Field ${flight.data?.field_id ?? "—"}`}
          />
        </Stack>
        <Typography variant="caption">Flight: {flightId}</Typography>
        <AgricultureJourneyStepper
          flightStatus={flight.data?.status}
          analysisStatus={runs.data?.[0]?.status}
          analysisRunId={runId}
        />
        {!browserOnline ? (
          <Alert severity="error" role="alert">
            This device is offline. Live controls are locked; last-known flight data remains visible and will refresh when connectivity returns.
          </Alert>
        ) : null}
        {flight.isError && flight.data ? (
          <Alert severity="warning" role="status">
            Showing stale flight data. Refresh will resume when the API is reachable.
          </Alert>
        ) : null}
        {sequenceGap || recoveredRuntimeEvents.data?.gap_detected ? (
          <Alert severity="warning">
            Live event sequence gap detected; replayed {recoveredRuntimeEvents.data?.events.length ?? 0} server events while state recovers.
          </Alert>
        ) : null}
        {runtime.connection !== "online" ? (
          <Alert
            severity={runtime.connection === "offline" ? "error" : "warning"}
            action={
              <Button size="small" onClick={runtime.reconnect}>
                Reconnect
              </Button>
            }
          >
            {runtime.connection === "offline"
              ? "Live link offline. Flight commands are disabled until the connection recovers."
              : "Live link degraded. State is read through safe polling/replay while reconnecting."}
          </Alert>
        ) : null}
        {event?.flight_id === flightId ? (
          <Typography
            component="p"
            variant="caption"
            color="text.secondary"
            aria-live="polite"
          >
            Last event: {event.name}
          </Typography>
        ) : null}
        <AgricultureLiveControls
          flightId={flightId}
          state={runtime.missionStatus?.mission_lifecycle?.state ?? flight.data?.status}
          online={browserOnline && runtime.connection === "online"}
          sequence={recoveredRuntimeEvents.data?.latest_sequence}
        />
        <Tabs
          value={stage}
          onChange={(_event, value: LiveStage) => setStage(value)}
          variant="scrollable"
          allowScrollButtonsMobile
          sx={{ borderBottom: 1, borderColor: "divider", minHeight: 36 }}
          aria-label="Agriculture flight stages"
        >
          <Tab label="Live" value="live" sx={{ minHeight: 36 }} />
          <Tab label="Media" value="media" sx={{ minHeight: 36 }} />
          <Tab label="Analysis" value="analysis" sx={{ minHeight: 36 }} />
        </Tabs>
        {stage === "live" ? (
          <Stack spacing={1}>
            <AgricultureLiveMap
              telemetry={runtime.telemetry}
              connection={runtime.connection}
              fieldId={flight.data?.field_id}
            />
            {recoveredRuntimeEvents.data?.events.length ? (
              <Stack component="section" aria-labelledby="agri-runtime-events-heading" spacing={0.5}>
                <Typography id="agri-runtime-events-heading" variant="subtitle2">Live event log</Typography>
                {recoveredRuntimeEvents.data.events.slice(-8).reverse().map((item, index) => (
                  <Typography key={`${String(item.sequence)}-${index}`} variant="caption" role="status">
                    #{String(item.sequence)} · {String(item.event_type ?? "runtime event")} · {String(item.state ?? "unknown")}
                  </Typography>
                ))}
              </Stack>
            ) : null}
            <FlightQualityPanel quality={q} coverage={c} />
            <MissionCommandPanel
              telemetry={runtime.telemetry}
              droneConnected={runtime.droneConnected}
              missionStatus={runtime.missionStatus}
              activeFlightId={flightId}
              title="Agriculture flight controls"
            />
          </Stack>
        ) : null}
        {stage === "media" ? (
          <Stack spacing={1}>
            <AgricultureMediaInventoryPanel flightId={flightId} />
            <AgricultureUploadPanel flightId={flightId} />
          </Stack>
        ) : null}
        {stage === "analysis" ? (
          <Stack spacing={1}>
            {!active && !runId ? (
              <AgricultureCapabilitySelector
                readiness={readiness.data}
                selected={selectedCapabilities}
                loading={readiness.isLoading}
                error={readiness.isError}
                pending={createRun.isPending || processRun.isPending}
                onSelected={(values) =>
                  setCapabilitySelection({
                    flightId: readiness.data?.flight_id ?? flightId,
                    values,
                  })
                }
                onRetry={() => void readiness.refetch()}
                onStart={() => void startPostFlight()}
              />
            ) : (
              <Alert severity="info">
                {active
                  ? "Finish the flight before starting post-flight analysis."
                  : "Analysis already started for this flight."}
              </Alert>
            )}
            {createRun.error || processRun.error ? (
              <Alert severity="error">
                Post-flight analysis could not start. Retry after the recording is
                finalized.
              </Alert>
            ) : null}
            {runs.data?.[0] ? (
              <AnalysisRunProgress
                status={runs.data[0].status}
                progress={runs.data[0].progress}
                error={runs.data[0].error}
                stages={analysisQuality.data?.stages ?? []}
                qualityGate={runs.data[0].quality_gate}
                retryCount={runs.data[0].retry_count}
                createdAt={runs.data[0].created_at}
              />
            ) : null}
          </Stack>
        ) : null}
      </Stack>
    </AgricultureAccessibilityBoundary>
  );
}
