import { Alert, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import type { LonLat } from "../../fields";
import type { MissionStatus } from "../../mission-workflow";

function isStartDisabled({
  name,
  altInput,
  sending,
  previewLoading,
  gridPreviewTooDense,
  gridPreviewError,
  fieldBorder,
}: {
  name: string;
  altInput: string;
  sending: boolean;
  previewLoading: boolean;
  gridPreviewTooDense: boolean;
  gridPreviewError: string | null | undefined;
  fieldBorder: LonLat[] | null;
}): boolean {
  return (
    sending ||
    previewLoading ||
    gridPreviewTooDense ||
    !!gridPreviewError ||
    !name.trim() ||
    altInput === "" ||
    Number(altInput) < 1 ||
    Number(altInput) > 500 ||
    !fieldBorder ||
    fieldBorder.length < 3
  );
}

export function FieldSurveyFlightSection({
  name,
  onNameChange,
  altInput,
  onAltInputChange,
  onAltBlur,
  sending,
  previewLoading,
  gridPreviewTooDense,
  gridPreviewError,
  fieldBorder,
  onSendMission,
  activeFlightId,
  missionStatus,
  embedded = false,
}: {
  name: string;
  onNameChange: (value: string) => void;
  altInput: string;
  onAltInputChange: (value: string) => void;
  onAltBlur: () => void;
  sending: boolean;
  previewLoading: boolean;
  gridPreviewTooDense: boolean;
  gridPreviewError: string | null | undefined;
  fieldBorder: LonLat[] | null;
  onSendMission: () => void;
  activeFlightId: string | null;
  missionStatus: MissionStatus | null;
  embedded?: boolean;
}) {
  const content = (
    <Stack spacing={2}>
      <TextField
        variant="filled"
        label="Mission name"
        value={name}
        onChange={(event) => onNameChange(event.target.value)}
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
        onChange={(event) => onAltInputChange(event.target.value)}
        onBlur={onAltBlur}
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
          disabled={isStartDisabled({
            name,
            altInput,
            sending,
            previewLoading,
            gridPreviewTooDense,
            gridPreviewError,
            fieldBorder,
          })}
          onClick={onSendMission}
        >
          {sending ? "Starting grid survey…" : "Start grid survey"}
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
