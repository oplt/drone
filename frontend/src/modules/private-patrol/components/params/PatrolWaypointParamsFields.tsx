import { FormControlLabel, Switch, TextField, Typography } from "@mui/material";
import InfoLabel from "../../../../shared/ui/InfoLabel";
import { INFO_INPUT_LABEL_PROPS } from "../../../mission-workflow";
import { PatrolScheduleFields } from "./PatrolScheduleFields";
import { PatrolSpeedField } from "./PatrolSpeedField";
import { PARAM_FIELD_SX } from "./patrolParamsLayout";
import type { PatrolParamsFieldProps } from "./patrolParamsTypes";

export function PatrolWaypointParamsFields({
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
  );
}
