import { Alert, Stack, Typography } from "@mui/material";

import { ActionIconButton } from "../../../shared/ui/ActionIconButton";

export function MissionSectionError({
  section,
  error,
  retrying = false,
  onRetry,
}: {
  section: string;
  error: unknown;
  retrying?: boolean;
  onRetry: () => void;
}) {
  const detail =
    error instanceof Error && error.message
      ? error.message
      : "Request failed. Try again.";

  return (
    <Alert
      severity="error"
      action={
        <ActionIconButton
          variant="retry"
          title={`Retry ${section}`}
          loading={retrying}
          onClick={onRetry}
        />
      }
    >
      <Stack spacing={0.25}>
        <Typography variant="body2" fontWeight={600}>
          {section} unavailable
        </Typography>
        <Typography variant="caption">{detail}</Typography>
      </Stack>
    </Alert>
  );
}
