import { useCallback } from "react";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    FormControlLabel,
    MenuItem,
    Paper,
    Stack,
    Switch,
    Tab,
    Tabs,
    TextField,
    Typography,
} from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { INFO_INPUT_LABEL_PROPS, MAX_GRID_PREVIEW_WAYPOINTS } from "../../mission-workflow";
import type { PatrolGridParams, PrivatePatrolMissionTaskType } from "../types";
import { effectivePatrolRepeatIntervalMinutes } from "../types";
import type { usePrivatePatrolMission } from "../hooks/usePrivatePatrolMission";
import type { PatrolSensorIntegration } from "../api/eventTriggerConfigApi";
import { EventTriggerConnectionPanel } from "./EventTriggerConnectionPanel";

type MissionVm = ReturnType<typeof usePrivatePatrolMission>;
type ParamsTab = PrivatePatrolMissionTaskType | "event_triggered";

const fieldSx = (width: number) =>
    ({
        flex: { xs: "1 1 100%", sm: `0 0 ${width}px` },
        width: { xs: "100%", sm: width },
        minWidth: { xs: 0, sm: width },
        maxWidth: "100%",
    }) as const;

const PARAM_FIELD_SX = {
    xxs: fieldSx(100),
    xs: fieldSx(125),
    s: fieldSx(150),
    m: fieldSx(170),
    l: fieldSx(200),
    xl: fieldSx(225),
    xxl: fieldSx(250),
} as const;

const PARAM_FULL_ROW_SX = {
    flex: "1 1 100%",
    width: "100%",
    minWidth: 0,
} as const;

const PARAM_GRID_SX = {
    display: "flex",
    flexWrap: "wrap",
    gap: 1.25,
    alignItems: "flex-start",
    justifyContent: "flex-start",
    "& .MuiTextField-root": {
        maxWidth: "100%",
    },
    "& .MuiInputBase-root": {
        minHeight: 58,
    },
    "& .MuiInputLabel-root": {
        maxWidth: "calc(100% - 24px)",
    },
    "& .MuiFormControlLabel-root": {
        m: 0,
        maxWidth: "100%",
        alignSelf: "center",
        "& .MuiFormControlLabel-label": {
            whiteSpace: "normal",
            lineHeight: 1.2,
        },
    },
} as const;

const AI_TASKS_SX = {
    display: "flex",
    flexWrap: "wrap",
    gap: 1,
    alignItems: "center",
    justifyContent: "flex-start",
} as const;

const PARAM_TABS: { value: ParamsTab; label: string }[] = [
    { value: "perimeter_patrol", label: "Perimeter Patrol" },
    { value: "waypoint_patrol", label: "Waypoint Patrol" },
    { value: "grid_surveillance", label: "Grid Surveillance" },
    { value: "event_triggered", label: "Event Triggered" },
];

export function PrivatePatrolParamsSection({
    mission,
    selectedFieldId,
    hasPropertyGeofence,
    eventTriggerIntegration,
    eventTriggerSaving,
    eventTriggerSaveError,
}: {
    mission: MissionVm;
    selectedFieldId: number | null;
    hasPropertyGeofence: boolean;
    eventTriggerIntegration: PatrolSensorIntegration | null;
    eventTriggerSaving?: boolean;
    eventTriggerSaveError?: string | null;
}) {
    const {
        gridParams,
        setGridParams,
        isWaypointPatrol,
        isGridSurveillance,
        isEventTriggeredPatrol,
        hasEventTriggerGeometry,
        hasRequiredTaskGeometry,
        eventLocation,
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
    } = mission;

    const activeTab: ParamsTab = gridParams.event_triggered_enabled
        ? "event_triggered"
        : gridParams.task_type;

    const handleTabChange = useCallback(
        (_: React.SyntheticEvent, value: ParamsTab) => {
            if (value === "event_triggered") {
                setGridParams((p) => ({ ...p, event_triggered_enabled: true }));
                return;
            }
            setGridParams((p) => ({
                ...p,
                task_type: value,
                event_triggered_enabled: false,
            }));
        },
        [setGridParams],
    );

    const speedField = (
        <TextField
            variant="filled"
            label={
                <InfoLabel
                    label="Speed (m/s)"
                    info={
                        activeTab === "waypoint_patrol"
                            ? "Waypoint patrol uses moderate speed for precise checkpoint approaches."
                            : activeTab === "grid_surveillance"
                                ? "Typical grid surveillance speed is 4–6 m/s for stable area coverage."
                                : activeTab === "event_triggered"
                                    ? "Event response uses moderate-to-high speed for rapid verification (typically 5–8 m/s)."
                                    : "Typical perimeter patrol speed is 5–8 m/s."
                    }
                />
            }
            InputLabelProps={INFO_INPUT_LABEL_PROPS}
            type="number"
            size="small"
            fullWidth
            sx={PARAM_FIELD_SX.xxs}
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
    );

    const scheduleFields = (
        <>
            <TextField
                variant="filled"
                label={
                    <InfoLabel
                        label="Start delay"
                        info="0 starts immediately. A positive value delays the first launch by this many minutes (page must stay open). When Repeat is 0, the same interval is used between subsequent flights."
                    />
                }
                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                type="number"
                size="small"
                fullWidth
                sx={PARAM_FIELD_SX.xs}
                value={gridParams.start_after_minutes}
                onChange={(e) => {
                    const value = Number(e.target.value);
                    if (!Number.isFinite(value)) return;
                    setGridParams((p) => ({
                        ...p,
                        start_after_minutes: Math.min(1440, Math.max(0, Math.round(value))),
                    }));
                }}
                inputProps={{ min: 0, max: 1440, step: 1 }}
            />
            <TextField
                variant="filled"
                label={
                    <InfoLabel
                        label="Repeat"
                        info="Minutes between flights after each successful landing. 0 uses Start delay for repeats when Start delay is set, otherwise repeat is off. Page must stay open."
                    />
                }
                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                type="number"
                size="small"
                fullWidth
                sx={PARAM_FIELD_SX.xxs}
                value={gridParams.repeat_interval_minutes}
                onChange={(e) => {
                    const value = Number(e.target.value);
                    if (!Number.isFinite(value)) return;
                    setGridParams((p) => ({
                        ...p,
                        repeat_interval_minutes: Math.min(1440, Math.max(0, Math.round(value))),
                    }));
                }}
                inputProps={{ min: 0, max: 1440, step: 1 }}
            />
        </>
    );

    return (
        <Box sx={{ mt: 1.5 }}>
            <Typography variant="subtitle2" sx={{ mb: 0.75, fontWeight: 700 }}>
                Parameters
            </Typography>
            <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                <Tabs
                    value={activeTab}
                    onChange={handleTabChange}
                    variant="scrollable"
                    scrollButtons="auto"
                    sx={{
                        mb: 1,
                        minHeight: 36,
                        borderBottom: 1,
                        borderColor: "divider",
                        "& .MuiTab-root": {
                            minHeight: 36,
                            py: 0.5,
                            px: 1.25,
                        },
                    }}
                >
                    {PARAM_TABS.map((tab) => (
                        <Tab key={tab.value} label={tab.label} value={tab.value} />
                    ))}
                </Tabs>

                <Box sx={PARAM_GRID_SX}>
                    {activeTab === "perimeter_patrol" && (
                        <>
                            {speedField}
                            {scheduleFields}
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
                                sx={PARAM_FIELD_SX.l}
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
                                        info="Typical property patrol offset is 10-30m from the property boundary."
                                    />
                                }
                                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                                type="number"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.xs}
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
                                sx={PARAM_FIELD_SX.xs}
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
                                        label="Camera angle (°)"
                                        info="Typical property patrol camera tilt is 30-45 degrees downward."
                                    />
                                }
                                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                                type="number"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.xs}
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
                                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                                type="number"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.xs}
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
                                        label="Max segment (m)"
                                        info="Smaller segments create smoother perimeter tracking."
                                    />
                                }
                                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                                type="number"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.xs}
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

                    {activeTab === "waypoint_patrol" && (
                        <>
                            {speedField}
                            {scheduleFields}
                            <TextField
                                variant="filled"
                                label={
                                    <InfoLabel
                                        label="Hover time"
                                        info="Hold 10-20 seconds at each key checkpoint for verification."
                                    />
                                }
                                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                                type="number"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.xs}
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
                                        label="Camera scan yaw"
                                        info="Set to 360° for full panorama scan at each key point."
                                    />
                                }
                                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                                type="number"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.m}
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
                                label={<Typography variant="body2">Zoom capture at checkpoints</Typography>}
                                sx={PARAM_FIELD_SX.xxl}
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
                                sx={PARAM_FIELD_SX.l}
                            />
                        </>
                    )}

                    {activeTab === "grid_surveillance" && (
                        <>
                            {speedField}
                            {scheduleFields}
                            <TextField
                                variant="filled"
                                select
                                label={
                                    <InfoLabel
                                        label="Pattern mode"
                                        info="Boustrophedon is a lawnmower sweep. Crosshatch adds a second pass."
                                    />
                                }
                                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.xl}
                                value={gridParams.grid_pattern_mode}
                                onChange={(e) =>
                                    setGridParams((p) => ({
                                        ...p,
                                        grid_pattern_mode: e.target.value as PatrolGridParams["grid_pattern_mode"],
                                    }))
                                }
                            >
                                <MenuItem value="boustrophedon">Boustrophedon (single pass)</MenuItem>
                                <MenuItem value="crosshatch">Crosshatch (two passes)</MenuItem>
                            </TextField>
                            {gridParams.grid_pattern_mode === "crosshatch" && (
                                <TextField
                                    variant="filled"
                                    label={
                                        <InfoLabel
                                            label="Crosshatch offset (°)"
                                            info="90 degrees gives an orthogonal second pass."
                                        />
                                    }
                                    InputLabelProps={INFO_INPUT_LABEL_PROPS}
                                    type="number"
                                    size="small"
                                    fullWidth
                                    sx={PARAM_FIELD_SX.m}
                                    value={gridParams.grid_crosshatch_angle_offset_deg}
                                    onChange={(e) => {
                                        const value = Number(e.target.value);
                                        if (!Number.isFinite(value)) return;
                                        setGridParams((p) => ({
                                            ...p,
                                            grid_crosshatch_angle_offset_deg: Math.min(179, Math.max(1, value)),
                                        }));
                                    }}
                                    inputProps={{ min: 1, max: 179, step: 1 }}
                                />
                            )}
                            <TextField
                                variant="filled"
                                select
                                label={
                                    <InfoLabel
                                        label="Lane strategy"
                                        info="Serpentine is efficient. One-way keeps each lane in the same direction."
                                    />
                                }
                                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.s}
                                value={gridParams.grid_lane_strategy}
                                onChange={(e) =>
                                    setGridParams((p) => ({
                                        ...p,
                                        grid_lane_strategy: e.target.value as PatrolGridParams["grid_lane_strategy"],
                                    }))
                                }
                            >
                                <MenuItem value="serpentine">Serpentine</MenuItem>
                                <MenuItem value="one_way">One-way lanes</MenuItem>
                            </TextField>
                            <TextField
                                variant="filled"
                                select
                                label="Start corner"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.xxs}
                                value={gridParams.grid_start_corner}
                                onChange={(e) =>
                                    setGridParams((p) => ({
                                        ...p,
                                        grid_start_corner: e.target.value as PatrolGridParams["grid_start_corner"],
                                    }))
                                }
                            >
                                <MenuItem value="auto">Auto</MenuItem>
                                <MenuItem value="sw">South-West</MenuItem>
                                <MenuItem value="se">South-East</MenuItem>
                                <MenuItem value="nw">North-West</MenuItem>
                                <MenuItem value="ne">North-East</MenuItem>
                            </TextField>
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
                                sx={PARAM_FIELD_SX.s}
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
                                        label="Row stride"
                                        info="1 flies every line. 2 flies every second line."
                                    />
                                }
                                InputLabelProps={INFO_INPUT_LABEL_PROPS}
                                type="number"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.xs}
                                value={gridParams.grid_row_stride}
                                onChange={(e) => {
                                    const value = Number(e.target.value);
                                    if (!Number.isFinite(value)) return;
                                    setGridParams((p) => ({
                                        ...p,
                                        grid_row_stride: Math.min(20, Math.max(1, Math.round(value))),
                                    }));
                                }}
                                inputProps={{ min: 1, max: 20, step: 1 }}
                            />
                            <TextField
                                variant="filled"
                                label="Row phase offset (m)"
                                type="number"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.m}
                                value={gridParams.grid_row_phase_m}
                                onChange={(e) => {
                                    const value = Number(e.target.value);
                                    if (!Number.isFinite(value)) return;
                                    setGridParams((p) => ({
                                        ...p,
                                        grid_row_phase_m: Math.max(0, value),
                                    }));
                                }}
                                inputProps={{ min: 0, max: 500, step: 0.5 }}
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
                                sx={PARAM_FIELD_SX.xs}
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
                                sx={PARAM_FIELD_SX.xs}
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

                    {activeTab === "event_triggered" && (
                        <>
                            {speedField}
                            <TextField
                                variant="filled"
                                label="Verification loiter (s)"
                                type="number"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.s}
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
                                sx={PARAM_FIELD_SX.m}
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
                                label="Target label"
                                size="small"
                                fullWidth
                                sx={PARAM_FIELD_SX.xs}
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
                                sx={PARAM_FIELD_SX.xs}
                            />
                            {!hasEventTriggerGeometry && (
                                <Alert severity="info" sx={{ py: 0.5, ...PARAM_FULL_ROW_SX }}>
                                    Set an event location on the map or use the saved property geofence
                                    for area search when coordinates are omitted.
                                </Alert>
                            )}
                            <EventTriggerConnectionPanel
                                integration={eventTriggerIntegration}
                                selectedFieldId={selectedFieldId}
                                hasGeofence={hasPropertyGeofence}
                                saving={eventTriggerSaving}
                                saveError={eventTriggerSaveError}
                            />
                            {eventLocation && (
                                <Chip
                                    size="small"
                                    color="error"
                                    variant="outlined"
                                    sx={{ flexBasis: "100%", width: "fit-content" }}
                                    label={`Event at ${eventLocation.lat.toFixed(5)}, ${eventLocation.lon.toFixed(5)}`}
                                />
                            )}
                        </>
                    )}

                    <Box sx={PARAM_FULL_ROW_SX}>
                        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 0.75 }}>
                            AI Tasks During Flight
                        </Typography>
                        <Box sx={AI_TASKS_SX}>
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
                                        sx={PARAM_FIELD_SX.s}
                                    />
                                );
                            })}
                        </Box>
                    </Box>

                    {isGridSurveillance && (alt < 20 || alt > 35) && (
                        <Alert severity="info" sx={{ py: 0.5, ...PARAM_FULL_ROW_SX }}>
                            Grid surveillance typically runs at 20-35m altitude for stable wide-area monitoring.
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
                            {typeof patrolPreviewStats?.path_offset_applied_m === "number" && (
                                <Chip
                                    size="small"
                                    variant="outlined"
                                    label={`Offset ${patrolPreviewStats!.path_offset_applied_m!.toFixed(1)} m`}
                                />
                            )}
                            {typeof patrolPreviewStats?.estimated_duration_s === "number" && (
                                <Chip
                                    size="small"
                                    variant="outlined"
                                    label={`ETA ${(patrolPreviewStats!.estimated_duration_s! / 60).toFixed(1)} min`}
                                />
                            )}
                        </Stack>
                    )}

                    {isEventTriggeredPatrol && hasEventTriggerGeometry && patrolPreviewStats?.response_mode && (
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
                        (scheduledStartAt != null || repeatWaitingForCompletion || repeatStartAt != null) && (
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
                </Box>
            </Paper>
        </Box>
    );
}