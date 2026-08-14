import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Stack,
} from "@mui/material";
import type { GridPreviewWaypoint } from "../../../mission-planning/types";
import { MAX_GRID_PREVIEW_WAYPOINTS } from "../../../mission-workflow";
import type { PatrolGridParams, PatrolPreviewStats } from "../../types";
import { effectivePatrolRepeatIntervalMinutes } from "../../types";
import { PARAM_FULL_ROW_SX } from "./patrolParamsLayout";

type PatrolPreviewStatusSectionProps = {
  gridParams: PatrolGridParams;
  isGridSurveillance: boolean;
  isWaypointPatrol: boolean;
  isEventTriggeredPatrol: boolean;
  hasEventTriggerGeometry: boolean;
  hasRequiredTaskGeometry: boolean;
  alt: number;
  gridPreview: GridPreviewWaypoint[] | null;
  patrolPreviewStats: PatrolPreviewStats | null;
  gridPreviewTooDense: boolean;
  gridPreviewError: string | null;
  previewLoading: boolean;
  scheduledStartAt: number | null;
  repeatStartAt: number | null;
  repeatWaitingForCompletion: boolean;
  cancelScheduledStart: () => void;
};

export function PatrolPreviewStatusSection({
  gridParams,
  isGridSurveillance,
  isWaypointPatrol,
  isEventTriggeredPatrol,
  hasEventTriggerGeometry,
  hasRequiredTaskGeometry,
  alt,
  gridPreview,
  patrolPreviewStats,
  gridPreviewTooDense,
  gridPreviewError,
  previewLoading,
  scheduledStartAt,
  repeatStartAt,
  repeatWaitingForCompletion,
  cancelScheduledStart,
}: PatrolPreviewStatusSectionProps) {
  return (
    <>
      {isGridSurveillance && (alt < 20 || alt > 35) && (
        <Alert severity="info" sx={{ py: 0.5, ...PARAM_FULL_ROW_SX }}>
          Grid surveillance typically runs at 20-35m altitude for stable wide-area
          monitoring.
        </Alert>
      )}

      {!isEventTriggeredPatrol && !hasRequiredTaskGeometry && (
        <Alert severity="info" sx={{ py: 0.5, ...PARAM_FULL_ROW_SX }}>
          {isWaypointPatrol
            ? "Add key points on the map (Gate, Parking, Storage, etc.) to generate a waypoint patrol preview."
            : "Draw or select a property polygon above to generate a patrol preview."}
        </Alert>
      )}

      {!isEventTriggeredPatrol && hasRequiredTaskGeometry && gridPreview && (
        <Stack
          direction="row"
          spacing={1}
          sx={{ flexWrap: "wrap", rowGap: 1, ...PARAM_FULL_ROW_SX }}
        >
          <Chip
            size="small"
            color="success"
            label={`${gridPreview.length} patrol waypoints`}
          />
          {typeof patrolPreviewStats?.total_route_m === "number" && (
            <Chip
              size="small"
              color="primary"
              variant="outlined"
              label={`Route ${patrolPreviewStats.total_route_m.toFixed(1)} m`}
            />
          )}
          {typeof patrolPreviewStats?.patrol_loops === "number" && (
            <Chip
              size="small"
              variant="outlined"
              label={`${patrolPreviewStats.patrol_loops} loop(s)`}
            />
          )}
          {typeof patrolPreviewStats?.key_points === "number" && (
            <Chip
              size="small"
              variant="outlined"
              label={`${patrolPreviewStats.key_points} checkpoints`}
            />
          )}
          {typeof patrolPreviewStats?.rows === "number" && (
            <Chip
              size="small"
              variant="outlined"
              label={`${patrolPreviewStats.rows} grid rows`}
            />
          )}
          {typeof patrolPreviewStats?.grid_spacing_m === "number" && (
            <Chip
              size="small"
              variant="outlined"
              label={`Spacing ${patrolPreviewStats.grid_spacing_m.toFixed(1)} m`}
            />
          )}
          {typeof patrolPreviewStats?.path_offset_applied_m === "number" && (
            <Chip
              size="small"
              variant="outlined"
              label={`Offset ${patrolPreviewStats.path_offset_applied_m.toFixed(1)} m`}
            />
          )}
          {typeof patrolPreviewStats?.estimated_duration_s === "number" && (
            <Chip
              size="small"
              variant="outlined"
              label={`ETA ${(patrolPreviewStats.estimated_duration_s / 60).toFixed(1)} min`}
            />
          )}
        </Stack>
      )}

      {isEventTriggeredPatrol &&
        hasEventTriggerGeometry &&
        patrolPreviewStats?.response_mode && (
          <Stack
            direction="row"
            spacing={1}
            sx={{ flexWrap: "wrap", rowGap: 1, ...PARAM_FULL_ROW_SX }}
          >
            <Chip
              size="small"
              variant="outlined"
              label={
                patrolPreviewStats.response_mode === "incident_response"
                  ? "Incident response"
                  : "Detection search"
              }
            />
          </Stack>
        )}

      {gridPreviewTooDense && !isWaypointPatrol && !isEventTriggeredPatrol && (
        <Alert severity="warning" sx={{ py: 0.5, ...PARAM_FULL_ROW_SX }}>
          Patrol preview is too dense ({gridPreview?.length}/{MAX_GRID_PREVIEW_WAYPOINTS}{" "}
          waypoints). Increase segment length or reduce patrol loops before launch.
        </Alert>
      )}

      {gridPreviewError && (
        <Alert severity="warning" sx={{ py: 0.5, ...PARAM_FULL_ROW_SX }}>
          {gridPreviewError}
        </Alert>
      )}

      {previewLoading && (
        <Box
          sx={{
            display: "flex",
            justifyContent: "center",
            ...PARAM_FULL_ROW_SX,
          }}
        >
          <CircularProgress size={20} />
        </Box>
      )}

      {!isEventTriggeredPatrol &&
        (scheduledStartAt != null ||
          repeatWaitingForCompletion ||
          repeatStartAt != null) && (
          <Alert
            severity="info"
            sx={{ py: 0.5, ...PARAM_FULL_ROW_SX }}
            action={
              <Button color="inherit" size="small" onClick={cancelScheduledStart}>
                Cancel
              </Button>
            }
          >
            {scheduledStartAt != null ? (
              <>
                Mission scheduled for {new Date(scheduledStartAt).toLocaleTimeString()}.
                {effectivePatrolRepeatIntervalMinutes(gridParams) > 0
                  ? ` Repeats every ${effectivePatrolRepeatIntervalMinutes(gridParams)} minute(s).`
                  : ""}
              </>
            ) : repeatWaitingForCompletion ? (
              <>Repeat armed. Interval starts after mission completes and drone lands.</>
            ) : (
              <>Next repeat scheduled for {new Date(repeatStartAt!).toLocaleTimeString()}.</>
            )}
          </Alert>
        )}
    </>
  );
}
