import { Chip, Stack } from "@mui/material";
import type { PatrolGridParams } from "../../types";
import { PARAM_FULL_ROW_SX } from "./patrolParamsLayout";
import type { PatrolParamsSetter } from "./patrolParamsTypes";

const GRID_PRESETS = [
  {
    label: "Wide area",
    patch: {
      grid_spacing_m: 25,
      grid_row_stride: 1,
      safety_inset_m: 2,
      grid_pattern_mode: "boustrophedon" as const,
    },
  },
  {
    label: "Dense cover",
    patch: {
      grid_spacing_m: 12,
      grid_row_stride: 1,
      safety_inset_m: 3,
      grid_pattern_mode: "crosshatch" as const,
      grid_crosshatch_angle_offset_deg: 90,
    },
  },
  {
    label: "Quick scan",
    patch: {
      grid_spacing_m: 35,
      grid_row_stride: 2,
      safety_inset_m: 1,
      grid_pattern_mode: "boustrophedon" as const,
    },
  },
] as const satisfies ReadonlyArray<{
  label: string;
  patch: Partial<PatrolGridParams>;
}>;

type PatrolGridPresetChipsProps = {
  setGridParams: PatrolParamsSetter;
};

export function PatrolGridPresetChips({ setGridParams }: PatrolGridPresetChipsProps) {
  return (
    <Stack
      direction="row"
      spacing={1}
      flexWrap="wrap"
      useFlexGap
      sx={{ ...PARAM_FULL_ROW_SX, mb: 0.5 }}
      aria-label="Grid surveillance presets"
    >
      {GRID_PRESETS.map((preset) => (
        <Chip
          key={preset.label}
          clickable
          size="small"
          label={preset.label}
          onClick={() => setGridParams((p) => ({ ...p, ...preset.patch }))}
          sx={{ minHeight: 36 }}
        />
      ))}
    </Stack>
  );
}
