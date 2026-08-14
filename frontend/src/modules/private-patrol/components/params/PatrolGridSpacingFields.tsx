import { TextField } from "@mui/material";
import InfoLabel from "../../../../shared/ui/InfoLabel";
import { INFO_INPUT_LABEL_PROPS } from "../../../mission-workflow";
import { PARAM_FIELD_SX } from "./patrolParamsLayout";
import type { PatrolParamsFieldProps } from "./patrolParamsTypes";

export function PatrolGridSpacingFields({
  gridParams,
  setGridParams,
}: Pick<PatrolParamsFieldProps, "gridParams" | "setGridParams">) {
  return (
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
  );
}
