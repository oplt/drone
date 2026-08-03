import { Alert, Chip, Stack, Typography } from "@mui/material";

export function FlightQualityPanel({
  quality,
  coverage,
}: {
  quality: Record<string, unknown>;
  coverage: Record<string, unknown>;
}) {
  const status = String(quality.status ?? "pending");
  return (
    <Stack
      component="section"
      aria-labelledby="flight-quality-heading"
      spacing={1}
    >
      <Typography id="flight-quality-heading" variant="subtitle2">
        Flight quality
      </Typography>
      <Stack
        role="status"
        aria-live="polite"
        direction="row"
        spacing={1}
        flexWrap="wrap"
        useFlexGap
      >
        <Chip
          size="small"
          label={`Quality: ${status}`}
          color={
            status === "blocked"
              ? "error"
              : status === "warning"
                ? "warning"
                : status === "pass"
                  ? "success"
                  : "default"
          }
        />
        <Chip
          size="small"
          variant="outlined"
          label={`Coverage: ${String(coverage.status ?? "pending")}`}
        />
        {typeof coverage.telemetry_gap_count === "number" &&
        coverage.telemetry_gap_count > 0 ? (
          <Chip
            size="small"
            color="warning"
            label={`Telemetry gaps: ${coverage.telemetry_gap_count}`}
          />
        ) : null}
      </Stack>
      {status === "blocked" ? (
        <Alert severity="error">
          Quality gate blocked inference. Review mapped poor areas and reflight
          them.
        </Alert>
      ) : null}
      {status === "pending" ? (
        <Alert severity="info">
          Quality evaluation starts after capture finalization.
        </Alert>
      ) : null}
    </Stack>
  );
}
