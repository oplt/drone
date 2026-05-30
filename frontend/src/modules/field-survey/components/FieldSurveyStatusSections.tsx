import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { MissionStatus } from "../../mission-workflow";
import type { useFieldSurveyIrrigation } from "../hooks/useFieldSurveyIrrigation";
import type { Waypoint } from "../../mission-workflow";

export function FieldSurveyStatusSections({
  waypoints,
  alt,
  missionStatus,
  activeFlightId,
  trackedMissionId,
  irrigation,
}: {
  waypoints: Waypoint[];
  alt: number;
  missionStatus: MissionStatus | null;
  activeFlightId: string | null;
  trackedMissionId: string | null;
  irrigation: ReturnType<typeof useFieldSurveyIrrigation>;
}) {
  return (
    <>
      {waypoints.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Waypoints
          </Typography>
          <Stack spacing={1}>
            {waypoints.map((wp, idx) => (
              <Typography key={idx} variant="body2">
                {idx + 1}. Lat: {wp.lat.toFixed(6)}, Lon: {wp.lon.toFixed(6)}, Alt:{" "}
                {wp.alt ?? alt}m
              </Typography>
            ))}
          </Stack>
        </Box>
      )}

      {missionStatus && (activeFlightId || waypoints.length > 0) && (
        <Box sx={{ mt: 2, p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: "bold", mb: 1 }}>
            Flight Status
          </Typography>
          <Stack spacing={0.5}>
            {missionStatus.flight_id && (
              <Typography variant="caption" component="div">
                Flight ID: {missionStatus.flight_id}
              </Typography>
            )}
            {missionStatus.mission_name && (
              <Typography variant="caption" component="div">
                Plan: {missionStatus.mission_name}
              </Typography>
            )}
            <Typography variant="caption" component="div">
              Telemetry:{" "}
              {missionStatus.telemetry?.running ? (
                <span style={{ color: "green" }}>Running</span>
              ) : (
                <span style={{ color: "red" }}>Stopped</span>
              )}
            </Typography>
            {missionStatus.telemetry?.active_connections !== undefined && (
              <Typography variant="caption" component="div">
                WS Connections: {missionStatus.telemetry.active_connections}
              </Typography>
            )}
            <Typography variant="caption" component="div">
              Drone Connected:{" "}
              {missionStatus.orchestrator?.drone_connected ? (
                <span style={{ color: "green" }}>Yes</span>
              ) : (
                <span style={{ color: "red" }}>No</span>
              )}
            </Typography>
          </Stack>
        </Box>
      )}

      {trackedMissionId && (
        <Box sx={{ mt: 2, p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            spacing={2}
            sx={{ mb: 1 }}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
              Irrigation Analysis
            </Typography>
            <ActionIconButton
              variant="upgrade"
              title="Reprocess"
              loading={irrigation.irrigationRefreshing}
              disabled={irrigation.irrigationRefreshing}
              onClick={() => void irrigation.reprocessIrrigation()}
            />
          </Stack>

          {irrigation.irrigationLoading ? (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={18} />
              <Typography variant="caption">Loading mission outputs...</Typography>
            </Stack>
          ) : irrigation.irrigationError ? (
            <Alert severity="warning">{irrigation.irrigationError}</Alert>
          ) : irrigation.irrigationSummary ? (
            <Stack spacing={1.2}>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Chip
                  size="small"
                  label={`Status: ${irrigation.irrigationSummary.status}`}
                  color={
                    irrigation.irrigationSummary.status === "completed"
                      ? "success"
                      : irrigation.irrigationSummary.status === "failed"
                        ? "error"
                        : "default"
                  }
                />
                <Chip
                  size="small"
                  label={`Captures: ${irrigation.irrigationSummary.capture_count}`}
                  variant="outlined"
                />
                <Chip
                  size="small"
                  label={`Dry: ${
                    irrigation.irrigationSummary.summary?.counts_by_type
                      ?.under_irrigated ?? 0
                  }`}
                  variant="outlined"
                />
                <Chip
                  size="small"
                  label={`Overwatered: ${
                    irrigation.irrigationSummary.summary?.counts_by_type
                      ?.overwatered ?? 0
                  }`}
                  variant="outlined"
                />
                <Chip
                  size="small"
                  label={`Bands: ${
                    irrigation.irrigationSummary.summary?.counts_by_type
                      ?.uneven_distribution ?? 0
                  }`}
                  variant="outlined"
                />
                <Chip
                  size="small"
                  label={`Avg confidence: ${(
                    Number(irrigation.irrigationSummary.summary?.average_confidence ?? 0) *
                    100
                  ).toFixed(0)}%`}
                  variant="outlined"
                />
              </Stack>

              {irrigation.irrigationSummary.layer?.error && (
                <Alert severity="error">{irrigation.irrigationSummary.layer.error}</Alert>
              )}

              {!irrigation.irrigationSummary.capture_count ? (
                <Alert severity="info">
                  No geotagged captures have been ingested for this mission yet.
                </Alert>
              ) : (
                <Typography variant="caption" component="div">
                  Latest mission: {trackedMissionId}. The stitched preview overlay,
                  anomaly polygons, and ranked inspection points appear on the map when
                  processing completes.
                </Typography>
              )}

              {irrigation.irrigationCapturePreview.length > 0 && (
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {irrigation.irrigationCapturePreview.map((capture) => (
                    <Chip
                      key={capture.id}
                      size="small"
                      label={`#${capture.id} @ ${capture.lat.toFixed(4)}, ${capture.lon.toFixed(
                        4
                      )}`}
                      variant="outlined"
                    />
                  ))}
                </Stack>
              )}

              {(irrigation.irrigationSummary.inspection_points ?? [])
                .slice(0, 3)
                .map((point, index) => (
                  <Typography key={point.id} variant="caption" component="div">
                    {index + 1}. {point.label} at {point.lat.toFixed(5)},{" "}
                    {point.lon.toFixed(5)}
                  </Typography>
                ))}
            </Stack>
          ) : (
            <Alert severity="info">
              Run a grid mission to generate irrigation outputs.
            </Alert>
          )}
        </Box>
      )}
    </>
  );
}
