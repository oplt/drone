import {
  Alert,
  Button,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { useState } from "react";
import {
  useAgricultureAnalysisRuns,
  useAgricultureFlight,
  useAgricultureFlightCoverage,
  useAgricultureFlightQuality,
  useAgricultureAnalysisQuality,
  useAgricultureRuntimeEvents,
  useCancelAgricultureAnalysisRun,
  useCreateAgricultureAnalysisRun,
  useProcessAgricultureAnalysisRun,
  useReplayAgricultureAnalysisRun,
  useRetryAgricultureAnalysisStage,
} from "../hooks";
import type { AgricultureEvent } from "../runtime";
import { AgricultureReviewWorkspace } from "./AgricultureReviewWorkspace";
import { AgricultureTemporalWorkspace } from "./AgricultureTemporalWorkspace";
import { AgricultureSensorFusionPanel } from "./AgricultureSensorFusionPanel";
import { AgricultureCropInsightsPanel } from "./AgricultureCropInsightsPanel";
import { AgricultureActionExportPanel } from "./AgricultureActionExportPanel";
import { AgricultureGovernanceAssistantPanel } from "./AgricultureGovernanceAssistantPanel";
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
  const [createdRun, setCreatedRun] = useState<{
    flightId: string;
    runId: string;
  } | null>(null);
  const createRun = useCreateAgricultureAnalysisRun();
  const processRun = useProcessAgricultureAnalysisRun();
  const cancelRun = useCancelAgricultureAnalysisRun();
  const replayRun = useReplayAgricultureAnalysisRun();
  const retryStage = useRetryAgricultureAnalysisStage();
  const runtime = useMissionRuntime({ onError: () => undefined, alwaysConnect: active });
  const browserOnline = useBrowserOnline();
  const recoveredRuntimeEvents = useAgricultureRuntimeEvents(flightId, active);
  const runId =
    runs.data?.[0]?.id ??
    (createdRun?.flightId === flightId ? createdRun.runId : null);
  const analysisQuality = useAgricultureAnalysisQuality(runId);
  if (!flightId)
    return (
      <Alert severity="info">
        Save field, configure agriculture profile, then start flight.
      </Alert>
    );
  if (flight.isLoading)
    return (
      <Stack
        role="status"
        aria-live="polite"
        direction="row"
        spacing={1}
        alignItems="center"
      >
        <CircularProgress size={18} />
        <Typography variant="body2">Loading agriculture flight…</Typography>
      </Stack>
    );
  if (flight.isError && !flight.data)
    return (
      <Alert
        severity="warning"
        action={
          <Button size="small" onClick={() => void flight.refetch()}>
            Retry
          </Button>
        }
      >
        Agriculture flight state unavailable. Live telemetry remains active;
        polling will retry.
      </Alert>
    );
  const q = (quality.data?.quality ?? {}) as Record<string, unknown>;
  const c = (coverage.data?.coverage ?? {}) as Record<string, unknown>;
  const startPostFlight = async () => {
    if (!flightId) return;
    const run = await createRun.mutateAsync(flightId);
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
        <AgricultureLiveMap telemetry={runtime.telemetry} connection={runtime.connection} />
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
        <AgricultureMediaInventoryPanel flightId={flightId} />
        <AgricultureUploadPanel flightId={flightId} />
        {!active && !runId ? (
          <Button
            size="small"
            variant="contained"
            onClick={() => void startPostFlight()}
            disabled={createRun.isPending || processRun.isPending}
          >
            Start post-flight field health analysis
          </Button>
        ) : null}
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
            onReplay={[
              "failed",
              "cancelled",
              "blocked_quality",
            ].includes(runs.data[0].status) ? () => runId && replayRun.mutate(runId) : undefined}
            replayPending={replayRun.isPending}
            onRetryStage={(stageName) => runId && retryStage.mutate({ runId, stageName })}
            retryStagePending={retryStage.isPending ? retryStage.variables?.stageName : null}
          />
        ) : null}
        {runId ? <AgricultureReviewWorkspace runId={runId} /> : null}
        {runId &&
        runs.data?.[0] &&
        ["queued", "running"].includes(runs.data[0].status) ? (
          <Button
            size="small"
            color="warning"
            onClick={() => cancelRun.mutate(runId)}
            disabled={cancelRun.isPending}
          >
            {cancelRun.isPending ? "Cancelling…" : "Cancel analysis"}
          </Button>
        ) : null}
        {runId &&
        runs.data?.[0] &&
        ["failed", "cancelled", "blocked_quality"].includes(
          runs.data[0].status,
        ) ? (
          <Button
            size="small"
            color="warning"
            onClick={() => replayRun.mutate(runId)}
            disabled={replayRun.isPending}
          >
            {replayRun.isPending ? "Replaying…" : "Replay analysis"}
          </Button>
        ) : null}
        {runId ? (
          <AgricultureSensorFusionPanel
            flightId={flightId}
            runId={runId}
            active={active}
          />
        ) : null}
        {runId ? <AgricultureCropInsightsPanel runId={runId} /> : null}
        {runId ? <AgricultureActionExportPanel runId={runId} /> : null}
        {runId ? <AgricultureGovernanceAssistantPanel runId={runId} /> : null}
        {!active && flight.data?.field_id ? (
          <AgricultureTemporalWorkspace
            fieldId={flight.data.field_id}
            currentFlightId={flightId}
          />
        ) : null}
      </Stack>
    </AgricultureAccessibilityBoundary>
  );
}
