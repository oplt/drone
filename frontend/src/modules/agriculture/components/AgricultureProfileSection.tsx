import { MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import type { AgricultureMissionProfile, AgricultureSensorType } from "../types";

type Props = {
  profile: AgricultureMissionProfile;
  onChange: (profile: AgricultureMissionProfile) => void;
};

const PRESET_VALUES: Record<
  AgricultureMissionProfile["preset"],
  Partial<AgricultureMissionProfile>
> = {
  early_stand_count: {
    target_gsd_cm: 1.5,
    speed_mps: 3,
    front_overlap_pct: 80,
    side_overlap_pct: 70,
    requested_analyses: ["quality", "stand_count"],
  },
  rgb_weed_water: {
    target_gsd_cm: 2,
    speed_mps: 5,
    front_overlap_pct: 70,
    side_overlap_pct: 60,
    requested_analyses: ["quality", "weed_detection", "standing_water", "coverage"],
  },
  repeat_monitoring: {
    target_gsd_cm: 2,
    speed_mps: 4,
    front_overlap_pct: 75,
    side_overlap_pct: 65,
    requested_analyses: ["quality", "coverage", "crop_health"],
    repeat_interval_days: 7,
  },
  multispectral_thermal: {
    target_gsd_cm: 3,
    speed_mps: 3,
    front_overlap_pct: 80,
    side_overlap_pct: 70,
    sensor_inventory: ["rgb", "multispectral", "thermal"],
    requested_analyses: ["quality", "coverage"],
  },
};

export function AgricultureProfileSection({ profile, onChange }: Props) {
  const update = (patch: Partial<AgricultureMissionProfile>) =>
    onChange({ ...profile, ...patch });
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1.25}>
        <Typography variant="subtitle2">Agriculture profile</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField
            select
            size="small"
            fullWidth
            label="Preset"
            value={profile.preset}
            onChange={(e) => {
              const preset = e.target
                .value as AgricultureMissionProfile["preset"];
              onChange({ ...profile, preset, ...PRESET_VALUES[preset] });
            }}
          >
            <MenuItem value="early_stand_count">Early stand count</MenuItem>
            <MenuItem value="rgb_weed_water">RGB weed + water</MenuItem>
            <MenuItem value="repeat_monitoring">Repeat monitoring</MenuItem>
            <MenuItem value="multispectral_thermal">
              Multispectral + thermal capture (research sensors)
            </MenuItem>
          </TextField>
          <TextField
            size="small"
            fullWidth
            label="Crop"
            value={profile.crop_type}
            onChange={(e) => update({ crop_type: e.target.value })}
          />
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField
            size="small"
            fullWidth
            label="Variety"
            value={profile.variety}
            onChange={(e) => update({ variety: e.target.value })}
          />
          <TextField
            size="small"
            fullWidth
            label="Growth stage"
            value={profile.growth_stage}
            onChange={(e) => update({ growth_stage: e.target.value })}
          />
          <TextField
            size="small"
            fullWidth
            label="Season"
            value={profile.season}
            onChange={(e) => update({ season: e.target.value })}
          />
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Target GSD (cm/px)"
            value={profile.target_gsd_cm}
            onChange={(e) => update({ target_gsd_cm: Number(e.target.value) })}
            inputProps={{ min: 0.1, step: 0.1 }}
          />
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Speed (m/s)"
            value={profile.speed_mps}
            onChange={(e) => update({ speed_mps: Number(e.target.value) })}
            inputProps={{ min: 0.1, step: 0.1 }}
          />
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Row spacing (m)"
            value={profile.expected_row_spacing_m ?? ""}
            onChange={(e) =>
              update({
                expected_row_spacing_m: e.target.value
                  ? Number(e.target.value)
                  : null,
              })
            }
            inputProps={{ min: 0.1, step: 0.1 }}
          />
          <TextField
            select
            size="small"
            fullWidth
            label="Camera"
            value={profile.camera_orientation}
            onChange={(e) =>
              update({
                camera_orientation: e.target
                  .value as AgricultureMissionProfile["camera_orientation"],
              })
            }
          >
            <MenuItem value="nadir">Nadir</MenuItem>
            <MenuItem value="oblique">Oblique</MenuItem>
          </TextField>
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Grid angle (°)"
            value={profile.grid_angle_deg ?? ""}
            onChange={(e) =>
              update({
                grid_angle_deg: e.target.value ? Number(e.target.value) : null,
              })
            }
            inputProps={{ min: 0, max: 179, step: 1 }}
          />
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Camera width (px)"
            value={profile.camera_resolution_width_px}
            onChange={(e) =>
              update({ camera_resolution_width_px: Number(e.target.value) })
            }
            inputProps={{ min: 64, step: 1 }}
          />
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Camera height (px)"
            value={profile.camera_resolution_height_px}
            onChange={(e) =>
              update({ camera_resolution_height_px: Number(e.target.value) })
            }
            inputProps={{ min: 64, step: 1 }}
          />
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Focal length (mm)"
            value={profile.focal_length_mm ?? ""}
            onChange={(e) =>
              update({
                focal_length_mm: e.target.value ? Number(e.target.value) : null,
              })
            }
            inputProps={{ min: 0.1, step: 0.1 }}
          />
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Row direction (°)"
            value={profile.row_direction_deg ?? ""}
            onChange={(e) =>
              update({
                row_direction_deg: e.target.value
                  ? Number(e.target.value)
                  : null,
              })
            }
            inputProps={{ min: 0, max: 359, step: 1 }}
          />
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Front overlap (%)"
            value={profile.front_overlap_pct}
            onChange={(e) =>
              update({ front_overlap_pct: Number(e.target.value) })
            }
            inputProps={{ min: 0, max: 95 }}
          />
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Side overlap (%)"
            value={profile.side_overlap_pct}
            onChange={(e) =>
              update({ side_overlap_pct: Number(e.target.value) })
            }
            inputProps={{ min: 0, max: 95 }}
          />
          <TextField
            size="small"
            type="number"
            fullWidth
            label="Repeat every (days)"
            value={profile.repeat_interval_days ?? ""}
            onChange={(e) =>
              update({
                repeat_interval_days: e.target.value
                  ? Number(e.target.value)
                  : null,
              })
            }
            inputProps={{ min: 1, max: 365 }}
          />
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Sensors: {profile.sensor_inventory.join(", ")} · Analyses:{" "}
          {profile.requested_analyses.join(", ")}
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField
            size="small"
            fullWidth
            label="Sensors (comma separated)"
            value={profile.sensor_inventory.join(", ")}
            onChange={(e) =>
              update({
                sensor_inventory: e.target.value
                  .split(",")
                  .map((value) => value.trim().toLowerCase())
                  .filter((value): value is AgricultureSensorType =>
                    ["rgb", "multispectral", "thermal", "stereo", "lidar"].includes(value),
                  ),
              })
            }
          />
          <TextField
            size="small"
            fullWidth
            label="Calibration IDs (comma separated)"
            value={profile.calibration_ids.join(", ")}
            onChange={(e) =>
              update({
                calibration_ids: e.target.value
                  .split(",")
                  .map((value) => value.trim())
                  .filter(Boolean),
              })
            }
          />
        </Stack>
        <Typography variant="caption" color="text.secondary">
          P0 records crop context + capture requirements. Diagnosis and
          prescriptions remain later stages. Multispectral index products stay
          research-blocked until ADR-003 is GO.
        </Typography>
      </Stack>
    </Paper>
  );
}
