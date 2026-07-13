import { Alert, Box, Button, LinearProgress, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";
import EmptyState from "./EmptyState";
import ErrorState from "./ErrorState";
import PageLoader from "./PageLoader";

export type FeatureStateProps = {
  loading?: boolean;
  refreshing?: boolean;
  stale?: boolean;
  error?: string | null;
  requestId?: string | null;
  onRetry?: () => void;
  empty?: { title: string; description?: string; action?: ReactNode };
  children: ReactNode;
};

/** Shared feature state contract: first load, stale refresh, empty, and retryable failure. */
export function FeatureState({
  loading = false,
  refreshing = false,
  stale = false,
  error = null,
  requestId = null,
  onRetry,
  empty,
  children,
}: FeatureStateProps) {
  if (loading && !stale) return <PageLoader title="Loading feature" />;
  if (error && !stale) {
    return <ErrorState message={error} requestId={requestId} onRetry={onRetry} />;
  }
  if (empty) {
    return (
      <Stack spacing={1}>
        {refreshing ? <LinearProgress aria-label="Refreshing" /> : null}
        <EmptyState {...empty} />
      </Stack>
    );
  }
  return (
    <Box sx={{ position: "relative" }}>
      {stale ? (
        <Alert severity="warning" variant="outlined" sx={{ mb: 1 }} role="status">
          Showing last known data{refreshing ? "; refreshing…" : "."}
        </Alert>
      ) : null}
      {refreshing ? <LinearProgress aria-label="Refreshing" /> : null}
      {children}
    </Box>
  );
}

export function ProcessingState({
  jobId,
  progress,
  status,
  onCancel,
  onRetry,
}: {
  jobId?: string | number | null;
  progress?: number | null;
  status: string;
  onCancel?: () => void;
  onRetry?: () => void;
}) {
  return (
    <Alert severity={status === "failed" ? "error" : "info"}>
      <Typography variant="body2">Processing: {status}</Typography>
      {jobId != null ? <Typography variant="caption">Job ID: {jobId}</Typography> : null}
      {typeof progress === "number" ? <LinearProgress variant="determinate" value={Math.max(0, Math.min(100, progress))} sx={{ mt: 1 }} /> : null}
      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
        {onCancel ? <Button size="small" onClick={onCancel}>Cancel</Button> : null}
        {onRetry ? <Button size="small" onClick={onRetry}>Retry</Button> : null}
      </Stack>
    </Alert>
  );
}
