import { TextField } from "@mui/material";
import InfoLabel from "../../../../shared/ui/InfoLabel";
import { INFO_INPUT_LABEL_PROPS } from "../../../mission-workflow";
import { PARAM_FIELD_SX } from "./patrolParamsLayout";
import type { PatrolParamsFieldProps } from "./patrolParamsTypes";

export function PatrolSpeedField({
  gridParams,
  setGridParams,
  activeTab,
}: PatrolParamsFieldProps) {
  return (
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
}
