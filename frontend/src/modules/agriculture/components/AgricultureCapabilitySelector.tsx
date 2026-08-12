import {
  Alert,
  Button,
  Checkbox,
  CircularProgress,
  FormControlLabel,
  Stack,
  Typography,
} from "@mui/material";
import type { AgricultureAnalysisReadiness } from "../types";

export function AgricultureCapabilitySelector({
  readiness,
  selected,
  loading,
  error,
  pending,
  onSelected,
  onRetry,
  onStart,
}: {
  readiness?: AgricultureAnalysisReadiness;
  selected: string[];
  loading: boolean;
  error: boolean;
  pending: boolean;
  onSelected: (selected: string[]) => void;
  onRetry: () => void;
  onStart: () => void;
}) {
  return (
    <Stack spacing={1} component="fieldset" sx={{ border: 0, p: 0, m: 0 }}>
      <Typography component="legend" variant="subtitle2">
        Available post-flight analyses
      </Typography>
      {loading ? (
        <CircularProgress size={18} aria-label="Checking analysis readiness" />
      ) : null}
      {error ? (
        <Alert
          severity="warning"
          action={<Button size="small" onClick={onRetry}>Retry</Button>}
        >
          Analysis readiness is unavailable.
        </Alert>
      ) : null}
      {readiness?.capture_prerequisites
        ?.filter((item) => !item.satisfied)
        .map((item) => (
          <Alert key={item.id} severity="info">
            {item.label}: {item.message}
          </Alert>
        ))}
      {readiness?.capabilities.map((capability) => (
        <FormControlLabel
          key={capability.id}
          disabled={!capability.available || pending}
          control={
            <Checkbox
              checked={selected.includes(capability.id)}
              onChange={(_, checked) =>
                onSelected(
                  checked
                    ? [...new Set([...selected, capability.id])]
                    : selected.filter((id) => id !== capability.id),
                )
              }
            />
          }
          label={
            <Stack>
              <Typography variant="body2">{capability.label}</Typography>
              <Typography variant="caption" color="text.secondary">
                {capability.available
                  ? capability.description
                  : capability.unavailable_reasons.join(" ")}
              </Typography>
            </Stack>
          }
        />
      ))}
      <Button
        size="small"
        variant="contained"
        onClick={onStart}
        disabled={!selected.length || !readiness?.ready || pending}
      >
        Start selected analyses
      </Button>
    </Stack>
  );
}
