import { TextField } from "@mui/material";
import InfoLabel from "../../../../shared/ui/InfoLabel";
import { INFO_INPUT_LABEL_PROPS } from "../../../mission-workflow";
import { PARAM_FIELD_SX } from "./patrolParamsLayout";
import type { PatrolParamsFieldProps } from "./patrolParamsTypes";

export function PatrolScheduleFields({
  gridParams,
  setGridParams,
}: Pick<PatrolParamsFieldProps, "gridParams" | "setGridParams">) {
  return (
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
}
