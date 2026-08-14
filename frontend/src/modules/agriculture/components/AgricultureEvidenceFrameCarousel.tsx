import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Chip,
  Stack,
  Typography,
} from "@mui/material";
import { selectDetectionEvidence } from "../../video-analysis/evidenceSelection";
import { useSearchParams } from "react-router-dom";
import { useAgricultureObservationEvidence } from "../hooks";
import { AgricultureEvidenceVideoPlayer } from "./AgricultureEvidenceVideoPlayer";

export function AgricultureEvidenceFrameCarousel({
  observationId,
}: {
  observationId: string | null;
}) {
  if (!observationId)
    return (
      <Alert severity="info">Select an observation to review evidence.</Alert>
    );

  return <ObservationEvidenceCarousel observationId={observationId} />;
}

function ObservationEvidenceCarousel({ observationId }: { observationId: string }) {
  const evidence = useAgricultureObservationEvidence(observationId);
  const [searchParams] = useSearchParams();
  if (evidence.isLoading)
    return (
      <Stack role="status" aria-live="polite" direction="row" spacing={1}>
        <CircularProgress size={16} />
        <Typography variant="caption">Loading evidence…</Typography>
      </Stack>
    );
  if (evidence.isError)
    return (
      <Alert
        severity="warning"
        action={
          <Button size="small" onClick={() => void evidence.refetch()}>
            Retry
          </Button>
        }
      >
        Evidence is unavailable or the signed link expired.
      </Alert>
    );
  if (!evidence.data?.assets.length)
    return (
      <Alert severity="info">
        No retained evidence asset is available for this observation.
      </Alert>
    );
  const requestedEvidenceId =
    searchParams.get("type") === "detection" ? searchParams.get("evidence") : null;
  const selected =
    evidence.data.assets.find((asset) => asset.evidence_id === requestedEvidenceId) ??
    evidence.data.assets[0];
  const selectedIsImage =
    selected.content_type?.startsWith("image/") || selected.source_kind !== "rgb_video";
  return (
    <Stack
      component="section"
      aria-labelledby="agriculture-evidence-heading"
      spacing={0.75}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography id="agriculture-evidence-heading" variant="subtitle2">
          Spatially linked evidence
        </Typography>
        <Chip size="small" color="primary" label="Selected map finding" />
      </Stack>
      <Stack direction="row" spacing={1} sx={{ overflowX: "auto", pb: 0.5 }}>
        {evidence.data.assets.map((asset) => (
          <Button
            key={asset.evidence_id}
            variant={asset.evidence_id === selected.evidence_id ? "contained" : "outlined"}
            aria-pressed={asset.evidence_id === selected.evidence_id}
            onClick={() => selectDetectionEvidence(asset.evidence_id)}
            sx={{ minWidth: 112, minHeight: 64, textTransform: "none" }}
          >
            <Stack alignItems="flex-start">
              <Typography variant="caption" fontWeight={700}>
                {asset.timestamp_seconds == null
                  ? "Source image"
                  : `${asset.timestamp_seconds.toFixed(3)}s`}
              </Typography>
              <Typography variant="caption">
                {asset.frame_index == null ? asset.source_kind : `Frame ${asset.frame_index}`}
              </Typography>
            </Stack>
          </Button>
        ))}
      </Stack>
      {selectedIsImage ? (
        <Box
          component="a"
          href={selected.signed_url}
          target="_blank"
          rel="noreferrer"
          aria-label={`Open source evidence ${selected.evidence_id}`}
          sx={{ display: "block", border: 2, borderColor: "primary.main", borderRadius: 1 }}
        >
          <Box
            component="img"
            src={selected.signed_url}
            alt={`Selected evidence for map finding ${selected.evidence_id}`}
            loading="lazy"
            sx={{ display: "block", width: "100%", maxHeight: 280, objectFit: "contain" }}
          />
        </Box>
      ) : null}
      {selected.source_video_id != null && selected.timestamp_seconds != null ? (
        <AgricultureEvidenceVideoPlayer
          videoId={selected.source_video_id}
          timestampSeconds={selected.timestamp_seconds}
        />
      ) : (
        <Typography variant="caption" color="text.secondary">
          Image-only evidence · no authorized source-video timestamp is available.
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary">
        Media {selected.media_id} · checksum {selected.checksum} · timestamp source{" "}
        {selected.timestamp_source ?? "image capture"}
      </Typography>
    </Stack>
  );
}
