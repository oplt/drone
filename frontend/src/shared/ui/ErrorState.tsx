import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

export type ErrorStateProps = {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  action?: ReactNode;
};

export default function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  retryLabel = "Try again",
  action,
}: ErrorStateProps) {
  return (
    <Box
      role="alert"
      aria-live="assertive"
      sx={{
        width: "100%",
        maxWidth: 560,
        mx: "auto",
        py: { xs: 4, md: 6 },
        px: { xs: 2, md: 3 },
      }}
    >
      <Stack spacing={2} alignItems="flex-start">
        <Typography variant="h5" component="h2">
          {title}
        </Typography>
        <Alert severity="error" sx={{ width: "100%" }}>
          {message}
        </Alert>
        {(onRetry || action) && (
          <Stack direction="row" spacing={1}>
            {onRetry ? (
              <Button variant="contained" onClick={onRetry}>
                {retryLabel}
              </Button>
            ) : null}
            {action}
          </Stack>
        )}
      </Stack>
    </Box>
  );
}
