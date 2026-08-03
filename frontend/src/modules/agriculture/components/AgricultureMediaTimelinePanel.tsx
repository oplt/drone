import { Alert, Button, Paper, Slider, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useAgricultureMediaTimeline, useAgricultureTelemetryWindow, useAgricultureTimelineBookmarks, useSaveAgricultureTimelineBookmark } from "../hooks";
import { AgricultureGeoJsonPreview } from "./AgricultureGeoJsonPreview";

export function AgricultureMediaTimelinePanel({ flightId }: { flightId: string }) {
  const timeline = useAgricultureMediaTimeline(flightId);
  const [index, setIndex] = useState(0);
  const [note, setNote] = useState("");
  const frame = timeline.data?.frames[Math.min(index, Math.max(0, (timeline.data?.frames.length ?? 1) - 1))];
  const telemetry = useAgricultureTelemetryWindow(flightId, frame?.timestamp_utc ?? null);
  const bookmarks = useAgricultureTimelineBookmarks(flightId);
  const saveBookmark = useSaveAgricultureTimelineBookmark();
  const bookmarked = Boolean(frame && bookmarks.data?.bookmarks.some((item) => item.frame_lineage_id === frame.id));
  useEffect(() => {
    const selectEvidenceFrame = (event: Event) => {
      const evidenceIds = (event as CustomEvent<{ evidenceIds?: unknown[] }>).detail?.evidenceIds;
      if (!Array.isArray(evidenceIds) || !timeline.data?.frames.length) return;
      const next = timeline.data.frames.findIndex((candidate) => evidenceIds.map(String).includes(candidate.id));
      if (next >= 0) setIndex(next);
    };
    window.addEventListener("agriculture:evidence-select", selectEvidenceFrame);
    return () => window.removeEventListener("agriculture:evidence-select", selectEvidenceFrame);
  }, [timeline.data?.frames]);
  const map = useMemo(() => frame?.footprint_geojson ? { features: [{ type: "Feature", geometry: frame.footprint_geojson, properties: { id: frame.id } }] } : { features: [] }, [frame]);
  if (timeline.isLoading) return <Typography variant="caption" role="status">Loading synchronized media timeline…</Typography>;
  if (timeline.isError) return <Alert severity="warning">Frame timeline unavailable. Evidence review remains available.</Alert>;
  if (!timeline.data?.frames.length) return <Alert severity="info">No georeferenced frame timeline is available for this flight.</Alert>;
  return (
    <Paper component="section" aria-labelledby="agriculture-media-timeline-heading" variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Typography id="agriculture-media-timeline-heading" variant="subtitle2">Frame, map and telemetry timeline</Typography>
        <Typography variant="caption" color="text.secondary">Frame {frame?.frame_index} · {frame ? new Date(frame.timestamp_utc).toLocaleString() : "—"} · GSD {frame?.gsd_cm ?? "—"} cm · telemetry links {frame?.telemetry_sample_before_id ?? "—"}/{frame?.telemetry_sample_after_id ?? "—"}</Typography>
        {frame?.signed_url && frame.content_type?.startsWith("image/") ? <img src={frame.signed_url} alt={`Agriculture frame ${frame.frame_index}`} loading="lazy" style={{ width: "100%", maxHeight: 320, objectFit: "contain" }} /> : frame?.signed_url && frame.content_type?.startsWith("video/") ? <video controls preload="metadata" src={frame.signed_url} aria-label={`Agriculture source video at frame ${frame.frame_index}`} style={{ width: "100%", maxHeight: 320 }} /> : frame?.signed_url ? <Button component="a" href={frame.signed_url} target="_blank" rel="noreferrer">Open source media</Button> : <Alert severity="info">Source media is unavailable or expired. Re-run media reconciliation or restore the retained artifact.</Alert>}
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button size="small" variant="outlined" onClick={() => setIndex((value) => Math.max(0, value - 1))} disabled={index === 0} aria-label="Previous frame">Previous frame</Button>
          <Button size="small" variant="outlined" onClick={() => setIndex((value) => Math.min((timeline.data?.frames.length ?? 1) - 1, value + 1))} disabled={index >= (timeline.data?.frames.length ?? 1) - 1} aria-label="Next frame">Next frame</Button>
          <Button size="small" variant={bookmarked ? "contained" : "outlined"} onClick={() => frame && saveBookmark.mutate({ flightId, frameLineageId: frame.id, note })} disabled={!frame || saveBookmark.isPending}>{bookmarked ? "Update bookmark" : "Bookmark frame"}</Button>
        </Stack>
        <TextField size="small" label="Frame note" value={note} onChange={(event) => setNote(event.target.value)} inputProps={{ maxLength: 1000, "aria-label": "Frame bookmark note" }} placeholder="Add context for review" />
        {saveBookmark.isError ? <Alert severity="error">Bookmark could not be saved. Retry when the connection is available.</Alert> : null}
        <Slider value={index} min={0} max={Math.max(0, timeline.data.frames.length - 1)} step={1} onChange={(_, value) => setIndex(Array.isArray(value) ? value[0] : value)} aria-label="Frame timeline" valueLabelDisplay="auto" />
        <AgricultureGeoJsonPreview geojson={map} />
        <Stack component="section" aria-labelledby="telemetry-window-heading" spacing={0.5}>
          <Typography id="telemetry-window-heading" variant="subtitle2">Synchronized telemetry</Typography>
          {telemetry.isLoading ? <Typography variant="caption" role="status">Loading telemetry around selected frame…</Typography> : telemetry.isError ? <Alert severity="warning">Telemetry window unavailable; frame lineage IDs remain visible.</Alert> : telemetry.data?.samples.length ? <>
            <Typography variant="caption">{telemetry.data.samples.length} samples · ±{telemetry.data.window_seconds}s · GPS {telemetry.data.samples[0].gps_quality ?? "—"}</Typography>
            <Stack component="ul" aria-label="Telemetry samples around selected frame" sx={{ m: 0, pl: 2.5, maxHeight: 120, overflow: "auto" }}>
              {telemetry.data.samples.slice(0, 12).map((sample) => <Typography component="li" variant="caption" key={sample.id}>{new Date(sample.timestamp_utc).toLocaleTimeString()} · alt {sample.relative_altitude_m ?? "—"}m · speed {sample.ground_speed_mps ?? "—"}m/s · {sample.lat.toFixed(5)}, {sample.lon.toFixed(5)}</Typography>)}
            </Stack>
            <svg viewBox="0 0 360 80" role="img" aria-label="Telemetry altitude and speed chart" style={{ width: "100%", minHeight: 80, background: "#f6f8fa", borderRadius: 4 }}>
              <polyline fill="none" stroke="#1565c0" strokeWidth="2" points={telemetry.data.samples.map((sample, sampleIndex) => `${10 + (sampleIndex / Math.max(1, telemetry.data.samples.length - 1)) * 340},${70 - Math.min(60, Math.max(0, Number(sample.relative_altitude_m ?? 0)))}`).join(" ")} />
              <text x="10" y="14" fontSize="10" fill="#263238">Altitude (m)</text>
            </svg>
          </> : <Alert severity="info">No telemetry samples surround this frame.</Alert>}
        </Stack>
      </Stack>
    </Paper>
  );
}
