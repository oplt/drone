import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Stack,
  TextField,
} from "@mui/material";
import { TaskControlFrame } from "../../../modules/mission-workflow";
import type { TelemetrySnapshot } from "../../mission-runtime/types/runtime";
import {
  MissionCommandPanel,
  MissionPreflightPanel,
} from "../../mission-runtime";
import type { MissionStatus } from "../../mission-workflow";
import type { PreflightRunResponse } from "../../mission-runtime";
import {
  PHOTOGRAMMETRY_ALT_MAX_M,
  PHOTOGRAMMETRY_ALT_MIN_M,
} from "../hooks/usePhotogrammetryMission";
import type { usePhotogrammetryMapping } from "../hooks/usePhotogrammetryMapping";
import type { usePhotogrammetryMission } from "../hooks/usePhotogrammetryMission";
import { PhotogrammetryMappingSection } from "./PhotogrammetryMappingSection";
import { PhotogrammetryProfileSection } from "./PhotogrammetryProfileSection";

type MissionVm = ReturnType<typeof usePhotogrammetryMission>;
type MappingVm = ReturnType<typeof usePhotogrammetryMapping>;

export function PhotogrammetryMissionControls({
  controlFrameExpanded,
  onControlFrameExpandedChange,
  apiBase,
  fieldBorder,
  preflightRun,
  telemetry,
  droneConnected,
  missionStatus,
  activeFlightId,
  mission,
  mapping,
  selectedFieldId,
  onOpen3DPlanning,
}: {
  controlFrameExpanded: boolean;
  onControlFrameExpandedChange: (expanded: boolean) => void;
  apiBase: string;
  fieldBorder: import("../../fields").LonLat[] | null;
  preflightRun: PreflightRunResponse | null;
  telemetry: TelemetrySnapshot | null;
  droneConnected: boolean;
  missionStatus: MissionStatus | null;
  activeFlightId: string | null;
  mission: MissionVm;
  mapping: MappingVm;
  selectedFieldId: number | null;
  onOpen3DPlanning: () => void;
}) {
  return (
    <Box
      sx={{
        width: { xs: "100%", md: controlFrameExpanded ? 620 : 360 },
        transition: "width 180ms ease",
      }}
    >
      <Stack spacing={2}>
        <TaskControlFrame
          expanded={controlFrameExpanded}
          onExpandedChange={onControlFrameExpandedChange}
        >
          <MissionPreflightPanel
            apiBase={apiBase}
            missionType="photogrammetry"
            preflightRun={preflightRun}
            telemetry={telemetry}
          />
          <MissionCommandPanel
            telemetry={telemetry}
            droneConnected={droneConnected}
            missionStatus={missionStatus}
            activeFlightId={activeFlightId}
            apiBase={apiBase}
          />
        </TaskControlFrame>

        <PhotogrammetryMappingSection
          mapping={mapping}
          selectedFieldId={selectedFieldId}
          onOpen3DPlanning={onOpen3DPlanning}
        />

        <TextField
          variant="filled"
          label="Mission name"
          value={mission.name}
          onChange={(e) => mission.setName(e.target.value)}
          size="small"
          fullWidth
          required
          error={!mission.name.trim()}
          helperText={!mission.name.trim() ? "Mission name is required" : " "}
        />

        <TextField
          variant="filled"
          label="Mapping altitude (m)"
          type="text"
          value={mission.altInput}
          onChange={(e) => mission.handleAltitudeInputChange(e.target.value)}
          onBlur={mission.normalizeAltitude}
          size="small"
          fullWidth
          inputProps={{ inputMode: "numeric", pattern: "\\d*" }}
          error={
            mission.altInput !== "" &&
            (Number(mission.altInput) < PHOTOGRAMMETRY_ALT_MIN_M ||
              Number(mission.altInput) > PHOTOGRAMMETRY_ALT_MAX_M)
          }
          helperText={
            mission.altInput !== "" &&
            (Number(mission.altInput) < PHOTOGRAMMETRY_ALT_MIN_M ||
              Number(mission.altInput) > PHOTOGRAMMETRY_ALT_MAX_M)
              ? `Recommended capture range is ${PHOTOGRAMMETRY_ALT_MIN_M}–${PHOTOGRAMMETRY_ALT_MAX_M}m`
              : `High-res mapping profile: ${PHOTOGRAMMETRY_ALT_MIN_M}–${PHOTOGRAMMETRY_ALT_MAX_M}m`
          }
        />

        <PhotogrammetryProfileSection
          profile={mission.photogrammetryProfile}
          onProfileChange={mission.setPhotogrammetryProfile}
        />

        <Button
          variant="contained"
          onClick={() => void mission.sendMission()}
          disabled={
            mission.sending ||
            mission.previewLoading ||
            mission.gridPreviewTooDense ||
            !!mission.gridPreviewError ||
            !mission.name.trim() ||
            mission.altInput === "" ||
            Number(mission.altInput) < PHOTOGRAMMETRY_ALT_MIN_M ||
            Number(mission.altInput) > PHOTOGRAMMETRY_ALT_MAX_M ||
            !fieldBorder ||
            fieldBorder.length < 3
          }
          fullWidth
          sx={{ mt: 1 }}
          color="success"
        >
          {mission.sending ? (
            <>
              <CircularProgress size={20} sx={{ mr: 1 }} />
              Starting PhotoGrammetry...
            </>
          ) : (
            "Start PhotoGrammetry"
          )}
        </Button>

        {activeFlightId && (
          <Alert severity="info" sx={{ mt: 2 }}>
            Active flight: {missionStatus?.mission_name || "Loading..."}
          </Alert>
        )}
      </Stack>
    </Box>
  );
}
