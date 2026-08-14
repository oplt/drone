import type { ReactNode } from "react";
import { Paper, Stack, Typography } from "@mui/material";
import { ErrorAlerts } from "../../../shared/ui/ErrorAlerts";
import { MissionStatusChips } from "../../mission-runtime";
import { radius } from "../../../shared/theme/themePrimitives";

export function MissionWorkflowShell({
  title,
  subtitle,
  droneConnected,
  wsConnected,
  telemetry,
  errors,
  onDismissError,
  onClearErrors,
  children,
}: {
  title: string;
  subtitle: string;
  droneConnected: boolean;
  wsConnected: boolean;
  telemetry?: unknown;
  errors: string[];
  onDismissError: (index: number) => void;
  onClearErrors: () => void;
  children: ReactNode;
}) {
  return (
    <Paper
      variant="opsPanel"
      sx={{
        width: "100%",
        p: 3,
        borderRadius: radius.md,
      }}
    >
      <Stack
        direction={{ xs: "column", md: "row" }}
        alignItems={{ xs: "flex-start", md: "center" }}
        justifyContent="space-between"
        sx={{ mb: 2 }}
        spacing={2}
      >
        <div>
          <Typography variant="h5">{title}</Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            {subtitle}
          </Typography>
        </div>
        <MissionStatusChips
          droneConnected={droneConnected}
          wsConnected={wsConnected}
          telemetry={telemetry}
        />
      </Stack>

      <ErrorAlerts
        errors={errors}
        onDismiss={onDismissError}
        onClearAll={onClearErrors}
      />

      {children}
    </Paper>
  );
}
