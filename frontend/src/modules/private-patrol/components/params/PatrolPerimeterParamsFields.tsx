import { MenuItem, TextField } from "@mui/material";
import InfoLabel from "../../../../shared/ui/InfoLabel";
import { INFO_INPUT_LABEL_PROPS } from "../../../mission-workflow";
import type { PatrolGridParams } from "../../types";
import { PatrolScheduleFields } from "./PatrolScheduleFields";
import { PatrolSpeedField } from "./PatrolSpeedField";
import { PARAM_FIELD_SX } from "./patrolParamsLayout";
import type { PatrolParamsFieldProps } from "./patrolParamsTypes";

export function PatrolPerimeterParamsFields({
  gridParams,
  setGridParams,
  activeTab,
}: PatrolParamsFieldProps) {
  return (
    <>
      <PatrolSpeedField
        gridParams={gridParams}
        setGridParams={setGridParams}
        activeTab={activeTab}
      />
      <PatrolScheduleFields gridParams={gridParams} setGridParams={setGridParams} />
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
  );
}
