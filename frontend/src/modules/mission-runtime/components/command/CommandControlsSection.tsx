import TimelineIcon from "@mui/icons-material/Timeline";
import {
  Alert,
  Button,
  CircularProgress,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
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

      <Stack direction="row" spacing={1}>
        <Button
          size="small"
          variant="outlined"
          fullWidth
          onClick={() => onIssueCommand("pause")}
          disabled={!flightId || !capabilities.pause || busyCommand !== null}
        >
          {busyCommand === "pause" ? <CircularProgress size={16} /> : "Pause"}
        </Button>
        <Button
          size="small"
          variant="outlined"
          fullWidth
          onClick={() => onIssueCommand("resume")}
          disabled={!flightId || !capabilities.resume || busyCommand !== null}
        >
          {busyCommand === "resume" ? <CircularProgress size={16} /> : "Resume"}
        </Button>
        <Button
          size="small"
          color="error"
          variant="contained"
          fullWidth
          onClick={() => onIssueCommand("abort")}
          disabled={!flightId || !capabilities.abort || busyCommand !== null}
        >
          {busyCommand === "abort" ? <CircularProgress size={16} color="inherit" /> : "Abort"}
        </Button>
      </Stack>
    </>
  );
}
