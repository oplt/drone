import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";

export type SaveIndicatorState = "idle" | "saving" | "saved" | "error" | "dirty";

export type SaveIndicatorProps = {
  state: SaveIndicatorState;
  /** Optional override labels. */
  labels?: Partial<Record<SaveIndicatorState, string>>;
  sx?: SxProps<Theme>;
};

const DEFAULT_LABELS: Record<SaveIndicatorState, string> = {
  idle: "Up to date",
  dirty: "Unsaved changes",
  saving: "Saving…",
  saved: "Saved",
  error: "Save failed",
};

/** Shared save/sync affordance for editors (labeling, settings, live ops). */
export function SaveIndicator({ state, labels, sx }: SaveIndicatorProps) {
  const text = labels?.[state] ?? DEFAULT_LABELS[state];

  return (
    <Stack
      direction="row"
      spacing={0.75}
      alignItems="center"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      sx={sx}
    >
      {state === "saving" ? (
        <CircularProgress size={14} aria-hidden />
      ) : null}
      {state === "saved" ? (
        <CheckCircleOutlineIcon color="success" fontSize="small" aria-hidden />
      ) : null}
      {state === "error" ? (
        <ErrorOutlineIcon color="error" fontSize="small" aria-hidden />
      ) : null}
      <Typography
        variant="body2"
        color={
          state === "error"
            ? "error.main"
            : state === "dirty"
              ? "warning.main"
              : "text.secondary"
        }
        sx={{ fontWeight: state === "dirty" || state === "error" ? 600 : 500 }}
      >
        {text}
      </Typography>
    </Stack>
  );
}
