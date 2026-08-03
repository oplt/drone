import {
  Alert,
  Button,
  Chip,
  Divider,
  MenuItem,
  Paper,
  Select,
  Slider,
  Stack,
  TextField,
  Typography,
  useMediaQuery,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import {
  useAgricultureComparisons,
  useAgricultureTimeline,
  useCompareAgricultureFlight,
  useCreateAgricultureAnnotation,
  useReviewAgricultureObservation,
} from "../hooks";
import { AgricultureGeoJsonPreview } from "./AgricultureGeoJsonPreview";
import { FlightTimeline } from "./FlightTimeline";

const TREND_COLORS: Record<
  string,
  "error" | "warning" | "success" | "info" | "default"
> = {
  new: "error",
  expanding: "error",
  stable: "info",
  improving: "success",
  resolved: "success",
};
const EMPTY_FLIGHTS: never[] = [];
const EMPTY_ROWS: never[] = [];

export function AgricultureTemporalWorkspace({
  fieldId,
  currentFlightId,
}: {
  fieldId: number | null;
  currentFlightId: string;
}) {
  const timeline = useAgricultureTimeline(fieldId);
  const changes = useAgricultureComparisons(currentFlightId);
  const compare = useCompareAgricultureFlight();
  const review = useReviewAgricultureObservation();
  const annotate = useCreateAgricultureAnnotation();
  const flights = timeline.data ?? EMPTY_FLIGHTS;
  const references = useMemo(
    () => flights.filter((flight) => flight.id !== currentFlightId),
    [currentFlightId, flights],
  );
  const [referenceFlightId, setReferenceFlightId] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState("split");
  const [blinkCurrent, setBlinkCurrent] = useState(true);
  const [timelineIndex, setTimelineIndex] = useState(0);
  const [annotationMode, setAnnotationMode] = useState(false);
  const [label, setLabel] = useState("agronomist_review");
  const [severity, setSeverity] = useState(0.5);
  const [notes, setNotes] = useState("");
  const [geometry, setGeometry] = useState("{}");
  const prefersReducedMotion = useMediaQuery(
    "(prefers-reduced-motion: reduce)",
  );
  const rows = changes.data ?? EMPTY_ROWS;
  const selected = rows.find((row) => row.id === selectedId) ?? rows[0] ?? null;
  const currentGeojson = useMemo(
    () => ({
      features: rows
        .filter((row) => row.state !== "resolved")
        .map((row) => ({
          type: "Feature",
          geometry: row.geometry_geojson,
          properties: {
            observation_id: row.id,
            severity: Math.max(
              0,
              Math.min(
                1,
                row.delta_intensity == null ? 0.5 : 0.5 + row.delta_intensity,
              ),
            ),
          },
        })),
    }),
    [rows],
  );
  const previousGeojson = useMemo(
    () => ({
      features: rows
        .map((row) => ({
          type: "Feature",
          geometry: row.reference_geometry_geojson,
          properties: { observation_id: row.id, severity: 0.5 },
        }))
        .filter(
          (feature) =>
            feature.geometry && Object.keys(feature.geometry).length > 0,
        ),
    }),
    [rows],
  );

  const activeReferenceFlightId = referenceFlightId || references[0]?.id || "";
  useEffect(() => {
    if (viewMode !== "blink" || prefersReducedMotion) return;
    const timer = window.setInterval(
      () => setBlinkCurrent((value) => !value),
      1200,
    );
    return () => window.clearInterval(timer);
  }, [prefersReducedMotion, viewMode]);
  useEffect(() => {
    if (selected)
      window.dispatchEvent(
        new CustomEvent("agriculture:evidence-select", {
          detail: { evidenceIds: selected.evidence_ids },
        }),
      );
  }, [selected]);

  const createAnnotation = () => {
    if (!selected?.current_observation_id) return;
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(geometry) as Record<string, unknown>;
    } catch {
      return;
    }
    annotate.mutate({
      observationId: selected.current_observation_id,
      payload: {
        status: "submitted",
        label,
        severity,
        geometry_geojson: parsed,
        evidence_ids: selected.evidence_ids,
        notes,
      },
    });
  };

  if (!fieldId) return null;
  const timelineValue =
    timelineIndex ||
    Math.max(
      0,
      flights.findIndex((flight) => flight.id === currentFlightId),
    );
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1.5}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          justifyContent="space-between"
          spacing={1}
        >
          <div>
            <Typography variant="subtitle2">
              Field timeline & change review
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Comparable flights only · rejected observations stay in audit
              history
            </Typography>
          </div>
          <Stack direction="row" spacing={1}>
            <Chip
              size="small"
              variant="outlined"
              label={`${flights.length} flights`}
            />
            <Chip
              size="small"
              variant="outlined"
              label={`${rows.length} changes`}
            />
          </Stack>
        </Stack>
        {timeline.isLoading ? (
          <Typography variant="caption">Loading flight timeline…</Typography>
        ) : flights.length < 2 ? (
          <Alert severity="info">
            A second quality-approved flight is required for temporal
            comparison.
          </Alert>
        ) : (
          <>
            <Stack
              direction={{ xs: "column", md: "row" }}
              spacing={1}
              alignItems={{ md: "center" }}
            >
              <Typography variant="caption">Reference</Typography>
              <Select
                size="small"
                value={activeReferenceFlightId}
                onChange={(event) => setReferenceFlightId(event.target.value)}
                inputProps={{ "aria-label": "Reference flight" }}
                sx={{ minWidth: { xs: "100%", md: 220 } }}
              >
                {references.map((flight) => (
                  <MenuItem key={flight.id} value={flight.id}>
                    {new Date(flight.created_at).toLocaleDateString()} ·{" "}
                    {flight.id.slice(0, 8)}
                  </MenuItem>
                ))}
              </Select>
              <Button
                size="small"
                variant="contained"
                onClick={() =>
                  activeReferenceFlightId &&
                  compare.mutate({
                    flightId: currentFlightId,
                    referenceFlightId: activeReferenceFlightId,
                  })
                }
                disabled={!activeReferenceFlightId || compare.isPending}
              >
                {compare.isPending ? "Comparing…" : "Compare flights"}
              </Button>
              <Select
                size="small"
                value={viewMode}
                onChange={(event) => setViewMode(event.target.value)}
                inputProps={{ "aria-label": "Comparison view" }}
              >
                <MenuItem value="split">Split</MenuItem>
                <MenuItem value="blink" disabled={prefersReducedMotion}>
                  Blink
                </MenuItem>
              </Select>
            </Stack>
            <FlightTimeline
              flights={flights}
              value={timelineValue}
              onChange={(next) => {
                setTimelineIndex(next);
                if (flights[next]?.id && flights[next].id !== currentFlightId)
                  setReferenceFlightId(flights[next].id);
              }}
            />
            {changes.isError || compare.isError ? (
              <Alert
                severity="warning"
                action={
                  <Button size="small" onClick={() => void changes.refetch()}>
                    Retry
                  </Button>
                }
              >
                Comparison unavailable. Select a compatible reference flight and
                retry.
              </Alert>
            ) : null}
            {rows.length ? (
              <>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                  {viewMode === "split" ? (
                    <>
                      <Stack sx={{ flex: 1 }}>
                        <Typography variant="caption">Current</Typography>
                        <AgricultureGeoJsonPreview
                          geojson={currentGeojson}
                          selectedId={selected?.id}
                          onSelect={setSelectedId}
                        />
                      </Stack>
                      <Stack sx={{ flex: 1 }}>
                        <Typography variant="caption">Previous</Typography>
                        <AgricultureGeoJsonPreview
                          geojson={previousGeojson}
                          selectedId={selected?.id}
                          onSelect={setSelectedId}
                        />
                      </Stack>
                    </>
                  ) : (
                    <Stack sx={{ flex: 1 }}>
                      <Typography variant="caption">
                        {blinkCurrent ? "Current" : "Previous"}
                      </Typography>
                      <AgricultureGeoJsonPreview
                        geojson={
                          blinkCurrent ? currentGeojson : previousGeojson
                        }
                        selectedId={selected?.id}
                        onSelect={setSelectedId}
                      />
                    </Stack>
                  )}
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  {viewMode === "blink"
                    ? prefersReducedMotion
                      ? "Blink disabled because reduced motion is enabled."
                      : "Blink alternates current and previous layers every 1.2 seconds."
                    : "Split compares current and previous geometries side by side."}
                </Typography>
                <Divider />
                <Stack
                  component="ul"
                  aria-label="Temporal change review list"
                  spacing={0.75}
                  sx={{
                    maxHeight: 280,
                    overflow: "auto",
                    listStyle: "none",
                    p: 0,
                    m: 0,
                  }}
                >
                  {rows.map((row) => (
                    <Stack
                      component="li"
                      key={row.id}
                      direction={{ xs: "column", sm: "row" }}
                      spacing={1}
                      alignItems={{ sm: "center" }}
                      sx={{
                        p: 0.75,
                        borderRadius: 1,
                        bgcolor:
                          selected?.id === row.id
                            ? "action.selected"
                            : "transparent",
                      }}
                    >
                      <Button
                        size="small"
                        onClick={() => setSelectedId(row.id)}
                        aria-label={`Select ${row.observation_type.replaceAll("_", " ")} change`}
                        sx={{
                          justifyContent: "flex-start",
                          textTransform: "none",
                          minWidth: 150,
                        }}
                      >
                        {row.observation_type.replaceAll("_", " ")}
                      </Button>
                      <Chip
                        size="small"
                        color={TREND_COLORS[row.state] ?? "default"}
                        label={row.state}
                      />
                      <Typography variant="caption" sx={{ flex: 1 }}>
                        {row.delta_area_m2 == null
                          ? "area unresolved"
                          : `${row.delta_area_m2 >= 0 ? "+" : ""}${row.delta_area_m2.toFixed(1)}m²`}{" "}
                        · confidence {Math.round(row.confidence * 100)}%
                      </Typography>
                      {row.current_observation_id ? (
                        <>
                          <Button
                            size="small"
                            color="success"
                            onClick={() =>
                              review.mutate({
                                id: row.current_observation_id as string,
                                payload: { status: "confirmed" },
                              })
                            }
                          >
                            Confirm
                          </Button>
                          <Button
                            size="small"
                            color="error"
                            onClick={() =>
                              review.mutate({
                                id: row.current_observation_id as string,
                                payload: { status: "rejected" },
                              })
                            }
                          >
                            Reject
                          </Button>
                        </>
                      ) : null}
                    </Stack>
                  ))}
                </Stack>
              </>
            ) : (
              <Alert severity="info">
                Run comparison to see new, expanding, stable, improving, and
                resolved observations.
              </Alert>
            )}
            <Stack spacing={1}>
              <Button
                size="small"
                variant={annotationMode ? "contained" : "outlined"}
                onClick={() => setAnnotationMode((value) => !value)}
                disabled={!selected?.current_observation_id}
              >
                {annotationMode
                  ? "Close annotation mode"
                  : "Open annotation mode"}
              </Button>
              {annotationMode && selected ? (
                <Stack
                  spacing={1}
                  sx={{
                    p: 1,
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1,
                  }}
                >
                  <TextField
                    size="small"
                    label="Class / label"
                    value={label}
                    onChange={(event) => setLabel(event.target.value)}
                  />
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="caption">Severity</Typography>
                    <Slider
                      size="small"
                      value={severity}
                      min={0}
                      max={1}
                      step={0.05}
                      onChange={(_, value) => setSeverity(value as number)}
                      sx={{ maxWidth: 180 }}
                      aria-label="Annotation severity"
                    />
                  </Stack>
                  <TextField
                    size="small"
                    label="Polygon GeoJSON"
                    multiline
                    minRows={3}
                    value={geometry}
                    onChange={(event) => setGeometry(event.target.value)}
                  />
                  <TextField
                    size="small"
                    label="Notes"
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                  />
                  <Button
                    size="small"
                    variant="contained"
                    onClick={createAnnotation}
                    disabled={annotate.isPending}
                  >
                    {annotate.isPending ? "Saving…" : "Submit annotation"}
                  </Button>
                  {annotate.isError ? (
                    <Alert severity="error">
                      Annotation save failed; draft remains editable.
                    </Alert>
                  ) : null}
                </Stack>
              ) : null}
            </Stack>
          </>
        )}
      </Stack>
    </Paper>
  );
}
