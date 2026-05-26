import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import type { SxProps, Theme } from "@mui/material/styles";
import { statusToChipColor } from "../preflight/preflightUtils";
import type { PreflightRunResponse, TelemetrySnapshot } from "../types";
import { useMissionPreflightRows } from "../hooks/useMissionPreflightRows";
import { PreflightCategoryTables } from "./preflight/PreflightCategoryTables";
import { PreflightStatusDot } from "./preflight/PreflightStatusDot";

export function MissionPreflightPanel({
  missionType = "route",
  preflightRun,
  telemetry,
  title = "Preflight",
  defaultExpanded = true,
  sx,
  apiBase,
}: {
  /** @deprecated Settings load no longer requires apiBase; kept for compatibility. */
  apiBase?: string;
  missionType?: string;
  preflightRun: PreflightRunResponse | null;
  telemetry: TelemetrySnapshot | null;
  title?: string;
  defaultExpanded?: boolean;
  sx?: SxProps<Theme>;
}) {
  void apiBase;

  const { rowsByCategory, loadingParams, paramsError } = useMissionPreflightRows({
    missionType,
    preflightRun,
    telemetry,
  });

  const overallStatus = preflightRun?.overall_status ?? "NOT_RUN";
  const summary = preflightRun?.report?.summary;
  const readyToArm =
    preflightRun?.can_start_mission ??
    (overallStatus === "PASS" || overallStatus === "WARN");

  return (
    <Accordion
      disableGutters
      defaultExpanded={defaultExpanded}
      sx={[
        {
          borderRadius: 2,
          border: "1px solid",
          borderColor: "divider",
          "&:before": { display: "none" },
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreRoundedIcon />}
        sx={{ px: 1, py: 0.1, minHeight: 0 }}
      >
        <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap">
          <Typography variant="subtitle1">{title}</Typography>
          <Chip size="small" label={overallStatus} color={statusToChipColor(overallStatus)} />
          {preflightRun?.preflight_run_id && (
            <Chip size="small" label={preflightRun.preflight_run_id} variant="outlined" />
          )}
        </Stack>
      </AccordionSummary>
      <AccordionDetails sx={{ px: 0.2, pb: 0.2, pt: 0.2 }}>
        <Stack spacing={1}>
          {typeof summary?.passed === "number" && (
            <Stack direction="row" spacing={0.2} flexWrap="wrap">
              <Chip size="small" color="success" label={`Pass ${summary.passed}`} />
              <Chip size="small" color="warning" label={`Warn ${summary.warned ?? 0}`} />
              <Chip size="small" color="error" label={`Fail ${summary.failed ?? 0}`} />
            </Stack>
          )}

          {loadingParams && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 0.2 }}>
              <CircularProgress size={18} />
            </Box>
          )}
          {paramsError && <Alert severity="warning">{paramsError}</Alert>}

          <PreflightCategoryTables rowsByCategory={rowsByCategory} />

          <Stack direction="row" spacing={1} alignItems="center" sx={{ pt: 0.25 }}>
            <PreflightStatusDot
              status={readyToArm ? "PASS" : "FAIL"}
              title={readyToArm ? "Ready to arm" : "Not ready to arm"}
            />
            <Typography variant="caption" sx={{ fontWeight: 700, letterSpacing: 0.5 }}>
              {readyToArm ? "READY TO ARM" : "NOT READY TO ARM"}
            </Typography>
          </Stack>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
