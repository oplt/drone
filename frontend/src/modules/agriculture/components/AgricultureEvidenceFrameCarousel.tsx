import {
  Alert,
  Button,
  CircularProgress,
  ImageList,
  ImageListItem,
  Stack,
  Typography,
} from "@mui/material";
import { useAgricultureObservationEvidence } from "../hooks";

export function AgricultureEvidenceFrameCarousel({
  observationId,
}: {
  observationId: string | null;
}) {
  const evidence = useAgricultureObservationEvidence(observationId);
  if (!observationId)
    return (
      <Alert severity="info">Select an observation to review evidence.</Alert>
    );
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
  return (
    <Stack
      component="section"
      aria-labelledby="agriculture-evidence-heading"
      spacing={0.75}
    >
      <Typography id="agriculture-evidence-heading" variant="subtitle2">
        Evidence frames
      </Typography>
      <ImageList
        cols={Math.min(3, evidence.data.assets.length)}
        gap={8}
        sx={{ m: 0 }}
      >
        {evidence.data.assets.map((asset) => (
          <ImageListItem key={asset.evidence_id}>
            <Button
              component="a"
              href={asset.signed_url}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open evidence ${asset.evidence_id}`}
              sx={{ display: "block", p: 0 }}
            >
              <img
                src={asset.signed_url}
                alt={`Evidence ${asset.evidence_id}`}
                loading="lazy"
              />
            </Button>
          </ImageListItem>
        ))}
      </ImageList>
    </Stack>
  );
}
