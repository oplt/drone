import { Alert, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import type { PrivatePatrolMissionStatus } from "../types";
import type { usePrivatePatrolMission } from "../hooks/usePrivatePatrolMission";

type MissionVm = ReturnType<typeof usePrivatePatrolMission>;

function startPatrolLabel(
  mission: MissionVm,
  sending: boolean,
): string {
  if (sending) {
    if (mission.isWaypointPatrol) return "Starting waypoint patrol…";
    if (mission.isGridSurveillance) return "Starting grid surveillance…";
    if (mission.isEventTriggeredPatrol) return "Starting event-triggered patrol…";
    return "Starting perimeter patrol…";
  }
  if (mission.isWaypointPatrol) return "Start waypoint patrol";
  if (mission.isGridSurveillance) return "Start grid surveillance";
  if (mission.isEventTriggeredPatrol) return "Start event-triggered patrol";
  return "Start perimeter patrol";
}

function isStartDisabled(mission: MissionVm): boolean {
  const {
    name,
    altInput,
    sending,
    previewLoading,
    gridPreviewTooDense,
    gridPreviewError,
    hasRequiredTaskGeometry,
    isWaypointPatrol,
  } = mission;

  return (
    sending ||
    previewLoading ||
    (gridPreviewTooDense && !isWaypointPatrol) ||
    !!gridPreviewError ||
    !name.trim() ||
    altInput === "" ||
    Number(altInput) < 1 ||
    Number(altInput) > 500 ||
    !hasRequiredTaskGeometry
  );
}

export function PrivatePatrolFlightSection({
  mission,
  onSendMission,
  activeFlightId,
  missionStatus,
  embedded = false,
}: {
  mission: MissionVm;
  onSendMission: () => void;
  activeFlightId: string | null;
  missionStatus: PrivatePatrolMissionStatus | null;
  embedded?: boolean;
}) {
  const {
    name,
    setName,
    altInput,
    handleAltitudeInputChange,
    normalizeAltitude,
    sending,
  } = mission;

  const content = (
    <Stack spacing={2}>
      <TextField
        variant="filled"
        label="Mission name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        size="small"
        fullWidth
        required
        error={!name.trim()}
        helperText={!name.trim() ? "Mission name is required" : " "}
      />

      <TextField
        variant="filled"
        label="Cruise altitude (m)"
        type="text"
        value={altInput}
        onChange={(event) => handleAltitudeInputChange(event.target.value)}
        onBlur={normalizeAltitude}
        size="small"
        fullWidth
        inputProps={{ inputMode: "numeric", pattern: "\\d*" }}
        error={altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)}
        helperText={
          altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)
            ? "Must be between 1–500m"
            : " "
        }
      />

      <Stack direction="row" justifyContent="flex-end">
        <Button
          variant="contained"
          color="success"
          disabled={isStartDisabled(mission)}
          onClick={onSendMission}
        >
          {startPatrolLabel(mission, sending)}
        </Button>
      </Stack>

      {activeFlightId ? (
        <Alert severity="info">
          Active flight: {missionStatus?.mission_name || "Loading…"}
        </Alert>
      ) : null}
    </Stack>
  );

  if (embedded) {
    return content;
  }

  return (
    <Paper variant="outlined" sx={{ p: 2, width: { xs: "100%", md: 360 } }}>
      <Typography variant="h6" sx={{ mb: 2 }}>
        Flight
      </Typography>
      {content}
    </Paper>
  );
}
