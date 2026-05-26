import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { INFO_INPUT_LABEL_PROPS, MAX_GRID_PREVIEW_WAYPOINTS } from "../../mission-workflow";
import type { PatrolGridParams, PatrolTriggerType } from "../types";
import type { usePrivatePatrolMission } from "../hooks/usePrivatePatrolMission";

type MissionVm = ReturnType<typeof usePrivatePatrolMission>;

export function PrivatePatrolParamsSection({ mission }: { mission: MissionVm }) {
  const {
    gridParams,
    setGridParams,
    isWaypointPatrol,
    isGridSurveillance,
    isEventTriggeredPatrol,
    hasRequiredTaskGeometry,
    eventLocation,
    alt,
    gridPreview,
    patrolPreviewStats,
    gridPreviewTooDense,
    gridPreviewError,
    previewLoading,
  } = mission;

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Private Patrol Parameters
      </Typography>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "1fr",
              md: "repeat(2, minmax(0, 1fr))",
              xl: "repeat(3, minmax(0, 1fr))",
            },
            gap: 1.5,
            alignItems: "start",
          }}
        >
          <TextField
            variant="filled"
            select
            label={
              <InfoLabel
                label="Mission task"
                info="Task profile for private property security missions."
              />
            }
            InputLabelProps={INFO_INPUT_LABEL_PROPS}
            size="small"
            fullWidth
            value={gridParams.task_type}
            onChange={(e) =>
              setGridParams((p) => ({
                ...p,
                task_type: e.target.value as PatrolGridParams["task_type"],
              }))
            }
          >
              <MenuItem value="perimeter_patrol">A. Perimeter Patrol Mission</MenuItem>
              <MenuItem value="waypoint_patrol">B. Waypoint Patrol (Key Points)</MenuItem>
              <MenuItem value="grid_surveillance">C. Grid Surveillance Mission</MenuItem>
              <MenuItem value="event_triggered_patrol">
                D. Event-Triggered Patrol
              </MenuItem>
            </TextField>
          <TextField
            variant="filled"
            label={
              <InfoLabel
                label="Speed (m/s)"
                info={
                  isWaypointPatrol
                    ? "Waypoint patrol uses moderate speed for precise checkpoint approaches."
                    : isGridSurveillance
                      ? "Typical grid surveillance speed is 4–6 m/s for stable area coverage."
                      : isEventTriggeredPatrol
                        ? "Event response missions prioritize rapid verification (typically 5-8 m/s)."
                      : "Typical perimeter patrol speed is 5–8 m/s."
                }
              />
            }
            InputLabelProps={INFO_INPUT_LABEL_PROPS}
            type="number"
            size="small"
            fullWidth
            value={gridParams.speed_mps}
            onChange={(e) => {
              const value = Number(e.target.value);
              if (!Number.isFinite(value)) return;
              setGridParams((p) => ({
                ...p,
                speed_mps: Math.min(20, Math.max(0.5, value)),
              }));
            }}
            inputProps={{ min: 0.5, max: 20, step: 0.1 }}
          />
          {gridParams.task_type === "perimeter_patrol" && (
            <>
              <TextField
                variant="filled"
                select
                label={
                  <InfoLabel
                    label="Direction"
                    info="Drone route direction around the perimeter."
                  />
                }
                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                size="small"
                fullWidth
                value={gridParams.direction}
                onChange={(e) =>
                  setGridParams((p) => ({
                    ...p,
                    direction: e.target.value as PatrolGridParams["direction"],
                  }))
                }
              >
                <MenuItem value="clockwise">Clockwise</MenuItem>
                <MenuItem value="counterclockwise">Counter-clockwise</MenuItem>
              </TextField>
              <TextField
                variant="filled"
                label={
                  <InfoLabel
                    label="Perimeter offset (m)"
                    info="Typical private patrol offset is 10–30m from the property boundary."
                  />
                }
                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                type="number"
                size="small"
                fullWidth
                value={gridParams.path_offset_m}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    path_offset_m: Math.max(0, value),
                  }));
                }}
                inputProps={{ min: 0, max: 120, step: 1 }}
              />
              <TextField
                variant="filled"
                label="Patrol loops"
                type="number"
                size="small"
                fullWidth
                value={gridParams.patrol_loops}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    patrol_loops: Math.min(200, Math.max(1, Math.round(value))),
                  }));
                }}
                inputProps={{ min: 1, max: 200, step: 1 }}
              />
              <TextField
                variant="filled"
                label={
                  <InfoLabel
                    label="Camera angle (° down)"
                    info="Typical private patrol camera tilt is 30–45° downward."
                  />
                }
                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                type="number"
                size="small"
                fullWidth
                value={gridParams.camera_angle_deg}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    camera_angle_deg: Math.min(90, Math.max(0, value)),
                  }));
                }}
                inputProps={{ min: 0, max: 90, step: 1 }}
              />
              <TextField
                variant="filled"
                label={
                  <InfoLabel
                    label="Camera overlap (%)"
                    info="Typical overlap for patrol verification imagery is 40–60%."
                  />
                }
                type="number"
                size="small"
                fullWidth
                value={gridParams.camera_overlap_pct}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    camera_overlap_pct: Math.min(95, Math.max(0, value)),
                  }));
                }}
                inputProps={{ min: 0, max: 95, step: 1 }}
              />
              <TextField
                variant="filled"
                label={
                  <InfoLabel
                    label="Max segment length (m)"
                    info="Smaller segments create smoother perimeter tracking."
                  />
                }
                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                type="number"
                size="small"
                fullWidth
                value={gridParams.max_segment_length_m}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    max_segment_length_m: Math.min(300, Math.max(2, value)),
                  }));
                }}
                inputProps={{ min: 2, max: 300, step: 1 }}
              />
            </>
          )}
          {gridParams.task_type === "waypoint_patrol" && (
            <>
              <TextField
                variant="filled"
                label={
                  <InfoLabel
                    label="Hover time (s)"
                    info="Hold 10-20 seconds at each key checkpoint for verification."
                  />
                }
                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                type="number"
                size="small"
                fullWidth
                value={gridParams.hover_time_s}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    hover_time_s: Math.min(300, Math.max(1, value)),
                  }));
                }}
                inputProps={{ min: 1, max: 300, step: 1 }}
              />
              <TextField
                variant="filled"
                label={
                  <InfoLabel
                    label="Camera scan yaw (°)"
                    info="Set to 360° for full panorama scan at each key point."
                  />
                }
                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                type="number"
                size="small"
                fullWidth
                value={gridParams.camera_scan_yaw_deg}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    camera_scan_yaw_deg: Math.min(360, Math.max(0, value)),
                  }));
                }}
                inputProps={{ min: 0, max: 360, step: 5 }}
              />
              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={gridParams.zoom_capture}
                    onChange={(e) =>
                      setGridParams((p) => ({
                        ...p,
                        zoom_capture: e.target.checked,
                      }))
                    }
                  />
                }
                label={
                  <Typography variant="body2">Zoom capture at checkpoints</Typography>
                }
              />
              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={gridParams.return_to_start}
                    onChange={(e) =>
                      setGridParams((p) => ({
                        ...p,
                        return_to_start: e.target.checked,
                      }))
                    }
                  />
                }
                label={<Typography variant="body2">Return to start key point</Typography>}
              />
            </>
          )}
          {gridParams.task_type === "grid_surveillance" && (
            <>
              <TextField
                variant="filled"
                label={
                  <InfoLabel
                    label="Grid spacing (m)"
                    info="Typical spacing is 30-50m for wide surveillance coverage."
                  />
                }
                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                type="number"
                size="small"
                fullWidth
                value={gridParams.grid_spacing_m}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    grid_spacing_m: Math.min(300, Math.max(2, value)),
                  }));
                }}
                inputProps={{ min: 2, max: 300, step: 1 }}
              />
              <TextField
                variant="filled"
                label={
                  <InfoLabel
                    label="Grid angle (°)"
                    info="Adjust heading of grid lanes to align with site shape."
                  />
                }
                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                type="number"
                size="small"
                fullWidth
                value={gridParams.grid_angle_deg}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    grid_angle_deg: Math.min(179, Math.max(0, value)),
                  }));
                }}
                inputProps={{ min: 0, max: 179, step: 1 }}
              />
              <TextField
                variant="filled"
                label="Safety inset (m)"
                type="number"
                size="small"
                fullWidth
                value={gridParams.safety_inset_m}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    safety_inset_m: Math.min(100, Math.max(0, value)),
                  }));
                }}
                inputProps={{ min: 0, max: 100, step: 0.5 }}
              />
            </>
          )}
          {gridParams.task_type === "event_triggered_patrol" && (
            <>
              <TextField
                variant="filled"
                select
                label="Trigger type"
                size="small"
                fullWidth
                value={gridParams.trigger_type}
                onChange={(e) =>
                  setGridParams((p) => ({
                    ...p,
                    trigger_type: e.target.value as PatrolTriggerType,
                  }))
                }
              >
                <MenuItem value="motion_sensor">Motion sensor</MenuItem>
                <MenuItem value="fence_alarm">Fence alarm</MenuItem>
                <MenuItem value="camera_detection">Camera detection</MenuItem>
                <MenuItem value="night_schedule">Night schedule</MenuItem>
                <MenuItem value="unknown_vehicle">Unknown vehicle</MenuItem>
              </TextField>
              <TextField
                variant="filled"
                label="Verification loiter (s)"
                type="number"
                size="small"
                fullWidth
                value={gridParams.verification_loiter_s}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    verification_loiter_s: Math.min(600, Math.max(0, value)),
                  }));
                }}
                inputProps={{ min: 0, max: 600, step: 1 }}
              />
              <TextField
                variant="filled"
                label="Verification radius (m)"
                type="number"
                size="small"
                fullWidth
                value={gridParams.verification_radius_m}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  if (!Number.isFinite(value)) return;
                  setGridParams((p) => ({
                    ...p,
                    verification_radius_m: Math.min(150, Math.max(0, value)),
                  }));
                }}
                inputProps={{ min: 0, max: 150, step: 1 }}
              />
              <TextField
                variant="filled"
                label="Target label (optional)"
                size="small"
                fullWidth
                value={gridParams.target_label}
                onChange={(e) =>
                  setGridParams((p) => ({
                    ...p,
                    target_label: e.target.value,
                  }))
                }
                placeholder="e.g. unknown vehicle"
              />
              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={gridParams.track_target}
                    onChange={(e) =>
                      setGridParams((p) => ({
                        ...p,
                        track_target: e.target.checked,
                      }))
                    }
                  />
                }
                label={<Typography variant="body2">Track target</Typography>}
              />
              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={gridParams.auto_stream_video}
                    onChange={(e) =>
                      setGridParams((p) => ({
                        ...p,
                        auto_stream_video: e.target.checked,
                      }))
                    }
                  />
                }
                label={<Typography variant="body2">Stream video to operator</Typography>}
              />
            </>
          )}
          <Box sx={{ gridColumn: "1 / -1" }}>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              AI Tasks During Flight
            </Typography>
            <Stack
              direction={{ xs: "column", md: "row" }}
              spacing={1}
              sx={{ mt: 0.5, flexWrap: "wrap", rowGap: 1 }}
            >
              {[
                ["intruder_detection", "Intruder detection"],
                ["vehicle_detection", "Vehicle detection"],
                ["fence_breach_detection", "Fence breach detection"],
                ["motion_detection", "Motion detection"],
              ].map(([taskId, label]) => {
                const task = taskId as PatrolGridParams["ai_tasks"][number];
                const checked = gridParams.ai_tasks.includes(task);
                return (
                  <FormControlLabel
                    key={task}
                    control={
                      <Switch
                        size="small"
                        checked={checked}
                        onChange={(e) => {
                          setGridParams((p) => {
                            if (e.target.checked) {
                              if (p.ai_tasks.includes(task)) return p;
                              return { ...p, ai_tasks: [...p.ai_tasks, task] };
                            }
                            const next = p.ai_tasks.filter((t) => t !== task);
                            return {
                              ...p,
                              ai_tasks: next.length > 0 ? next : p.ai_tasks,
                            };
                          });
                        }}
                      />
                    }
                    label={<Typography variant="caption">{label}</Typography>}
                  />
                );
              })}
            </Stack>
          </Box>
          {isGridSurveillance && (alt < 20 || alt > 35) && (
            <Alert severity="info" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
              Grid surveillance typically runs at 20-35m altitude for stable wide-area monitoring.
            </Alert>
          )}
          {!hasRequiredTaskGeometry && (
            <Alert severity="info" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
              {isWaypointPatrol
                ? "Add key points on the map (Gate, Parking, Storage, etc.) to generate a waypoint patrol preview."
                : isEventTriggeredPatrol
                  ? "Set an event location point on the map. For night schedule trigger, a property polygon can be used as fallback."
                : "Draw or select a property polygon above to generate a patrol preview."}
            </Alert>
          )}
          {isEventTriggeredPatrol && eventLocation && (
            <Chip
              size="small"
              color="error"
              variant="outlined"
              sx={{ gridColumn: "1 / -1", width: "fit-content" }}
              label={`Event at ${eventLocation.lat.toFixed(5)}, ${eventLocation.lon.toFixed(5)}`}
            />
          )}
          {hasRequiredTaskGeometry && gridPreview && (
            <Stack
              direction="row"
              spacing={1}
              sx={{ flexWrap: "wrap", rowGap: 1, gridColumn: "1 / -1" }}
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
                  label={`Route ${patrolPreviewStats!.total_route_m!.toFixed(1)} m`}
                />
              )}
              {typeof patrolPreviewStats?.patrol_loops === "number" && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`${patrolPreviewStats!.patrol_loops} loop(s)`}
                />
              )}
              {typeof patrolPreviewStats?.key_points === "number" && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`${patrolPreviewStats!.key_points} checkpoints`}
                />
              )}
              {typeof patrolPreviewStats?.rows === "number" && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`${patrolPreviewStats!.rows} grid rows`}
                />
              )}
              {typeof patrolPreviewStats?.grid_spacing_m === "number" && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Spacing ${patrolPreviewStats!.grid_spacing_m!.toFixed(1)} m`}
                />
              )}
              {patrolPreviewStats?.trigger_type && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Trigger ${patrolPreviewStats!.trigger_type}`}
                />
              )}
              {patrolPreviewStats?.trigger_action && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Action ${patrolPreviewStats!.trigger_action}`}
                />
              )}
              {typeof patrolPreviewStats?.path_offset_applied_m === "number" && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Offset ${patrolPreviewStats!.path_offset_applied_m!.toFixed(
                    1
                  )} m`}
                />
              )}
              {typeof patrolPreviewStats?.estimated_duration_s === "number" && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`ETA ${(patrolPreviewStats!.estimated_duration_s! / 60).toFixed(
                    1
                  )} min`}
                />
              )}
            </Stack>
          )}
          {gridPreviewTooDense && !isWaypointPatrol && (
            <Alert severity="warning" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
              Patrol preview is too dense ({gridPreview?.length}/
              {MAX_GRID_PREVIEW_WAYPOINTS} waypoints). Increase segment
              length or reduce patrol loops before launch.
            </Alert>
          )}
          {gridPreviewError && (
            <Alert severity="warning" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
              {gridPreviewError}
            </Alert>
          )}
          {previewLoading && (
            <Box
              sx={{
                display: "flex",
                justifyContent: "center",
                gridColumn: "1 / -1",
              }}
            >
              <CircularProgress size={20} />
            </Box>
          )}
        </Box>
      </Paper>
    </Box>
  );
}
