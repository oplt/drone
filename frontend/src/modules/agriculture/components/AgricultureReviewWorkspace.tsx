import {
  Alert,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { selectDetectionEvidence } from "../../video-analysis/evidenceSelection";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  useAgricultureAnalysisQuality,
  useAgricultureLayer,
  useAgricultureObservationPage,
  useAgricultureSpatialViewport,
  useAgricultureSpatialLayers,
} from "../hooks";
import { CoverageMapLayer } from "./CoverageMapLayer";
import { HealthLayerSwitcher } from "./HealthLayerSwitcher";
import { ObservationMap } from "./ObservationMap";
import { ObservationReviewDrawer } from "./ObservationReviewDrawer";
import { RGBProductPanel } from "./RGBProductPanel";

const OBSERVATION_LAYERS = new Set([
  "all",
  "weed",
  "standing_water",
  "stand_count",
  "emergence_issue",
  "abnormal_crop_health_signature",
  "agriculture_anomaly",
]);

export function AgricultureReviewWorkspace({
  runId,
}: {
  runId: string | null;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const layer = searchParams.get("layer") || "all";
  const parsedConfidence = Number(searchParams.get("confidence") ?? "0.35");
  const threshold = Number.isFinite(parsedConfidence) ? parsedConfidence : 0.35;
  const [minSeverity, setMinSeverity] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const quality = useAgricultureAnalysisQuality(runId);
  const [pageCursors, setPageCursors] = useState<Array<string | undefined>>([
    undefined,
  ]);
  const pageCursor = pageCursors[pageCursors.length - 1];
  const observations = useAgricultureObservationPage(runId, {
    minConfidence: threshold,
    cursor: pageCursor,
    limit: 500,
  });
  const layerData = useAgricultureLayer(runId, layer === "all" ? null : layer);
  const spatial = useAgricultureSpatialViewport(runId, {
    layer,
    zoom: 12,
    minSeverity,
    minConfidence: threshold,
  });
  const spatialLayers = useAgricultureSpatialLayers(runId);
  const rows = useMemo(
    () =>
      (observations.data?.items ?? []).filter(
        (row) =>
          (layer === "all" || row.observation_type === layer) &&
          row.severity >= minSeverity,
      ),
    [layer, minSeverity, observations.data?.items],
  );
  const selected = rows.find((row) => row.id === selectedId) ?? rows[0] ?? null;
  const virtualized = rows.length > 100;
  const visibleRows = virtualized ? rows.slice(0, 100) : rows;

  const setLayer = (next: string) => {
    const params = new URLSearchParams(searchParams);
    params.set("layer", next);
    setSearchParams(params, { replace: true });
  };
  const setThreshold = (next: number) => {
    const params = new URLSearchParams(searchParams);
    params.set("confidence", String(next));
    setSearchParams(params, { replace: true });
  };

  useEffect(() => {
    // Reset pagination whenever the confidence filter changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPageCursors([undefined]);
  }, [threshold]);

  useEffect(() => {
    if (selected?.evidence_ids.length)
      selectDetectionEvidence(selected.evidence_ids[0]);
  }, [selected]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  if (!runId)
    return (
      <Alert severity="info">
        Start post-flight analysis to open the field-health workspace.
      </Alert>
    );
  if (quality.isLoading)
    return (
      <Stack
        role="status"
        aria-live="polite"
        direction="row"
        spacing={1}
        alignItems="center"
      >
        <CircularProgress size={16} />
        <Typography variant="caption">Loading quality gate…</Typography>
      </Stack>
    );
  if (quality.isError)
    return (
      <Alert
        severity="error"
        action={
          <Button size="small" onClick={() => void quality.refetch()}>
            Retry
          </Button>
        }
      >
        Quality gate unavailable; analysis review is temporarily paused.
      </Alert>
    );

  const summary = quality.data?.summary ?? {};
  const mapGeojson = OBSERVATION_LAYERS.has(layer)
    ? (spatial.data?.geojson ?? {
        features: rows.map((row) => ({
          type: "Feature",
          geometry: row.geometry_geojson,
          properties: {
            observation_id: row.id,
            observation_type: row.observation_type,
            severity: row.severity,
            confidence: row.confidence,
          },
        })),
      })
    : layerData.data?.geojson ?? { features: [] };

  return (
    <Paper
      component="section"
      aria-labelledby="agriculture-health-workspace-heading"
      variant="outlined"
      sx={{ p: 1.5 }}
    >
      <Stack spacing={1.5}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          justifyContent="space-between"
          spacing={1}
        >
          <div>
            <Typography
              id="agriculture-health-workspace-heading"
              variant="subtitle2"
            >
              Field health workspace
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Post-flight source of truth · run {runId}
            </Typography>
          </div>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Chip
              size="small"
              color={
                quality.data?.status === "blocked"
                  ? "error"
                  : quality.data?.status === "warning"
                    ? "warning"
                    : "success"
              }
              label={`Quality ${quality.data?.status ?? "pending"}`}
            />
            <Chip
              size="small"
              variant="outlined"
              label={`Score ${Math.round(Number(quality.data?.score ?? 0) * 100)}%`}
            />
            <Chip
              size="small"
              variant="outlined"
              label={`Issues ${rows.length}`}
            />
            <Chip
              size="small"
              variant="outlined"
              label={`Page ${pageCursors.length} · ${observations.data?.total ?? 0} total`}
            />
          </Stack>
        </Stack>
        {quality.data?.status === "blocked" ? (
          <Alert severity="error">
            Quality gate blocked downstream inference. Review evidence and
            reflight low-quality areas.
          </Alert>
        ) : null}
        {spatial.data?.partial ? (
          <Alert severity="info">
            Map is showing clustered or partial spatial data for performance. Use
            the keyboard review list and page controls for the complete result set.
          </Alert>
        ) : null}
        {spatialLayers.data?.layers.find((item) => item.layer === layer && item.status !== "ready") ? (
          <Alert severity="warning">
            This layer is {spatialLayers.data.layers.find((item) => item.layer === layer)?.status};
            displayed data may be stale or incomplete.
          </Alert>
        ) : null}
        <HealthLayerSwitcher
          layer={layer}
          onLayerChange={setLayer}
          confidence={threshold}
          onConfidenceChange={setThreshold}
          severity={minSeverity}
          onSeverityChange={setMinSeverity}
        />
        <Typography variant="caption" color="text.secondary" aria-live="polite">
          {String(summary.reasons ?? "").replaceAll("_", " ") ||
            "Quality metrics, coverage, and georeferenced observations are versioned per run."}
        </Typography>
        <RGBProductPanel products={(quality.data?.summary?.rgb_products as Record<string, unknown> | undefined) ?? {}} />
        {quality.data?.summary ? (
          <Typography variant="caption" color="text.secondary">
            Frames: {String(quality.data.summary.frame_count ?? 0)} · blocked:{" "}
            {String(quality.data.summary.blocked_frames ?? 0)} · telemetry:{" "}
            {String(
              (
                quality.data.summary.telemetry as
                  | Record<string, unknown>
                  | undefined
              )?.status ?? "unknown",
            )}
          </Typography>
        ) : null}
        {layer === "quality" ? (
          <CoverageMapLayer geojson={mapGeojson} />
        ) : (
          <ObservationMap
            geojson={mapGeojson}
            selectedId={selected?.id}
            onSelect={setSelectedId}
          />
        )}
        {layerData.isError ? (
          <Alert severity="info">
            This layer has no persisted GeoJSON yet; unresolved issues remain in
            the review list.
          </Alert>
        ) : null}
        <Divider />
        {OBSERVATION_LAYERS.has(layer) ? (
          observations.isLoading ? (
            <Stack role="status" aria-live="polite">
              <CircularProgress size={18} />
            </Stack>
          ) : observations.isError ? (
            <Alert
              severity="warning"
              action={
                <Button
                  size="small"
                  onClick={() => void observations.refetch()}
                >
                  Retry
                </Button>
              }
            >
              Observation layer unavailable.
            </Alert>
          ) : (
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
              <Stack
                component="ul"
                aria-label="Observation review list"
                spacing={0.75}
                sx={{
                  minWidth: { md: 320 },
                  maxHeight: 300,
                  overflow: "auto",
                  listStyle: "none",
                  p: 0,
                  m: 0,
                }}
              >
                {visibleRows.length ? (
                  visibleRows.map((row) => (
                    <li key={row.id}>
                      <Button
                        fullWidth
                        variant={
                          selected?.id === row.id ? "contained" : "outlined"
                        }
                        color={
                          row.review_state === "confirmed"
                            ? "success"
                            : "primary"
                        }
                        onClick={() => {
                          setSelectedId(row.id);
                          setDrawerOpen(true);
                        }}
                        aria-label={`Review ${row.observation_type.replaceAll("_", " ")}`}
                        sx={{
                          justifyContent: "space-between",
                          textTransform: "none",
                        }}
                      >
                        <span>{row.observation_type.replaceAll("_", " ")}</span>
                        <span>
                          {Math.round(row.confidence * 100)}% ·{" "}
                          {row.area_m2 == null
                            ? "unresolved"
                            : `${row.area_m2.toFixed(1)}m²`}
                        </span>
                      </Button>
                    </li>
                  ))
                ) : (
                  <Alert component="li" severity="info">
                    No observations match this layer and confidence threshold.
                  </Alert>
                )}
              </Stack>
              {virtualized ? (
                <Typography variant="caption" color="text.secondary">
                  Showing first 100 of {rows.length} matches. Narrow layer or
                  confidence, or use paging below.
                </Typography>
              ) : null}
              <Drawer
                anchor="right"
                open={drawerOpen && Boolean(selected)}
                onClose={() => setDrawerOpen(false)}
                PaperProps={{ sx: { width: { xs: "100%", sm: 420 }, p: 2 } }}
              >
                <ObservationReviewDrawer
                  observation={selected}
                  onClose={() => setDrawerOpen(false)}
                />
              </Drawer>
            </Stack>
          )
        ) : null}
        {OBSERVATION_LAYERS.has(layer) && observations.data ? (
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            flexWrap="wrap"
            useFlexGap
            spacing={1}
            aria-label="Observation page navigation"
          >
            <Typography variant="caption" color="text.secondary">
              Showing up to 500 observations in the current viewport page;
              use page navigation for large runs.
            </Typography>
            <Stack direction="row" spacing={1}>
              <Button
                size="small"
                variant="outlined"
                disabled={pageCursors.length === 1 || observations.isFetching}
                onClick={() =>
                  setPageCursors((current) => current.slice(0, -1))
                }
              >
                Previous page
              </Button>
              <Button
                size="small"
                variant="outlined"
                disabled={!observations.data.next_cursor || observations.isFetching}
                onClick={() =>
                  observations.data?.next_cursor &&
                  setPageCursors((current) => [
                    ...current,
                    observations.data?.next_cursor as string,
                  ])
                }
              >
                Next page
              </Button>
            </Stack>
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  );
}
