import type { ReactNode } from "react";
import { Paper, Stack, Typography } from "@mui/material";
import Header from "../../../shared/layout/WorkflowHeader";
import { ErrorAlerts } from "../../../shared/ui/ErrorAlerts";
import { MissionStatusChips } from "../../mission-runtime";

export function MissionWorkflowShell({
  title,
  subtitle,
  droneConnected,
  wsConnected,
  errors,
  onDismissError,
  onClearErrors,
  children,
}: {
  title: string;
  subtitle: string;
  droneConnected: boolean;
  wsConnected: boolean;
  errors: string[];
  onDismissError: (index: number) => void;
  onClearErrors: () => void;
  children: ReactNode;
}) {
  return (
    <>
      <Header />
      <Paper
        sx={{
          width: "100%",
          p: 3,
          borderRadius: 3,
          backgroundColor: "background.paper",
          border: "1px solid",
          borderColor: "divider",
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
          />
        </Stack>

        <ErrorAlerts
          errors={errors}
          onDismiss={onDismissError}
          onClearAll={onClearErrors}
        />

        {children}
      </Paper>
    </>
  );
}
