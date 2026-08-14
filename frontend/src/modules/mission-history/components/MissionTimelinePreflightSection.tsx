import { useId, useState } from "react";
import {
  Box,
  Collapse,
  IconButton,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import WarningIcon from "@mui/icons-material/Warning";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import { useTheme } from "@mui/material/styles";

import { formatMissionTimelineTs } from "../utils/missionTimelineFormat";
import { MissionTimelineStatusBadge } from "./MissionTimelineStatusBadge";

type PreflightCheck = {
  status?: string;
  name?: string;
  message?: string;
};

type PreflightData = {
  overall_status?: string;
  summary?: { passed?: number; warned?: number; failed?: number };
  started_at?: number;
  completed_at?: number;
  base_checks?: PreflightCheck[];
  mission_checks?: PreflightCheck[];
};

export function MissionTimelinePreflightSection({ data }: { data: PreflightData }) {
  const [open, setOpen] = useState(false);
  const contentId = useId();
  const theme = useTheme();

  const statusColor =
    data.overall_status === "PASS"
      ? theme.palette.success.main
      : data.overall_status === "WARN"
        ? theme.palette.warning.main
        : theme.palette.error.main;

  const allChecks = [...(data.base_checks ?? []), ...(data.mission_checks ?? [])];

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1} justifyContent="space-between">
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box
            sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: statusColor, flexShrink: 0 }}
          />
          <Typography fontWeight={600}>Preflight</Typography>
          <MissionTimelineStatusBadge status={data.overall_status ?? "unknown"} />
          {data.summary && (
            <Typography variant="caption" color="text.secondary">
              {data.summary.passed ?? 0} pass · {data.summary.warned ?? 0} warn ·{" "}
              {data.summary.failed ?? 0} fail
            </Typography>
          )}
        </Stack>
        <IconButton
          size="small"
          aria-label={open ? "Collapse preflight details" : "Expand preflight details"}
          aria-expanded={open}
          aria-controls={contentId}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
        </IconButton>
      </Stack>
      {data.started_at && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
          {formatMissionTimelineTs(data.started_at)} → {formatMissionTimelineTs(data.completed_at)}
        </Typography>
      )}
      <Collapse id={contentId} in={open}>
        <Stack spacing={0.5} sx={{ mt: 1.5 }}>
          {allChecks.map((check, index) => (
            <Stack key={index} direction="row" alignItems="center" spacing={1}>
              {check.status === "PASS" ? (
                <CheckCircleIcon fontSize="small" color="success" />
              ) : check.status === "WARN" ? (
                <WarningIcon fontSize="small" color="warning" />
              ) : (
                <ErrorIcon fontSize="small" color="error" />
              )}
              <Typography variant="body2" sx={{ flex: 1 }}>
                {check.name}
              </Typography>
              {check.message && (
                <Typography variant="caption" color="text.secondary">
                  {check.message}
                </Typography>
              )}
            </Stack>
          ))}
          {allChecks.length === 0 && (
            <Typography variant="caption" color="text.secondary">
              No checks recorded.
            </Typography>
          )}
        </Stack>
      </Collapse>
    </Paper>
  );
}
