import TimelineIcon from "@mui/icons-material/Timeline";
import {
  Alert,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import { ActionIconButton } from "../../../../shared/ui/ActionIconButton";
import type { MissionCommand, MissionLifecycleSlice } from "../../types";

export function CommandControlsSection({
  flightId,
  lifecycle,
  capabilities,
  busyCommand,
  message,
  error,
  onIssueCommand,
}: {
  flightId: string | null;
  lifecycle: MissionLifecycleSlice | null;
  capabilities: { pause: boolean; resume: boolean; abort: boolean };
  busyCommand: MissionCommand | null;
  message: string | null;
  error: string | null;
  onIssueCommand: (command: MissionCommand) => void;
}) {
  const navigate = useNavigate();

  return (
    <>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="body2" color="text.secondary">
          Mission Controls
        </Typography>
        <Stack direction="row" alignItems="center" spacing={0.5}>
          <Typography
            variant="caption"
            sx={{ fontFamily: "monospace", color: "text.secondary" }}
          >
            {flightId ? `flight ${flightId}` : "no active flight"}
          </Typography>
          {flightId && (
            <Tooltip title="View mission timeline">
              <IconButton
                size="small"
                onClick={() => navigate(`/missions/${flightId}/timeline`)}
                aria-label="View mission timeline"
              >
                <TimelineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Stack>
      </Stack>

      {!flightId && <Alert severity="info">Start a mission to enable controls.</Alert>}
      {lifecycle?.last_error && (
        <Alert severity="error">Last mission error: {lifecycle.last_error}</Alert>
      )}
      {error && <Alert severity="error">{error}</Alert>}
      {message && <Alert severity="success">{message}</Alert>}

      <Stack direction="row" spacing={0.25}>
        <ActionIconButton
          variant="pause"
          title="Pause"
          loading={busyCommand === "pause"}
          disabled={!flightId || !capabilities.pause || busyCommand !== null}
          onClick={() => onIssueCommand("pause")}
        />
        <ActionIconButton
          variant="resume"
          title="Resume"
          loading={busyCommand === "resume"}
          disabled={!flightId || !capabilities.resume || busyCommand !== null}
          onClick={() => onIssueCommand("resume")}
        />
        <ActionIconButton
          variant="abort"
          title="Abort"
          color="error"
          loading={busyCommand === "abort"}
          disabled={!flightId || !capabilities.abort || busyCommand !== null}
          onClick={() => onIssueCommand("abort")}
        />
      </Stack>
    </>
  );
}
