import { MenuItem, TextField } from "@mui/material";
import InfoLabel from "../../../../shared/ui/InfoLabel";
import { INFO_INPUT_LABEL_PROPS } from "../../../mission-workflow";
import type { PatrolGridParams } from "../../types";
import { PARAM_FIELD_SX } from "./patrolParamsLayout";
import type { PatrolParamsFieldProps } from "./patrolParamsTypes";

export function PatrolGridPatternFields({
  gridParams,
  setGridParams,
}: Pick<PatrolParamsFieldProps, "gridParams" | "setGridParams">) {
  return (
    <>
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
    </>
  );
}
