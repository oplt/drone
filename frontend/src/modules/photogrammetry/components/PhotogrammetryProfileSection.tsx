import {
  Box,
  FormControlLabel,
  MenuItem,
  Paper,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { INFO_INPUT_LABEL_PROPS } from "../../mission-workflow";
import type { PhotogrammetryProfile } from "../hooks/usePhotogrammetryMission";

export function PhotogrammetryProfileSection({
  profile,
  onProfileChange,
}: {
  profile: PhotogrammetryProfile;
  onProfileChange: React.Dispatch<React.SetStateAction<PhotogrammetryProfile>>;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Mapping Mission Profile
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: 1,
        }}
      >
        <TextField
          variant="filled"
          size="small"
          label="Front overlap (%)"
          type="number"
          value={profile.front_overlap_pct}
          onChange={(e) => {
            const value = Number(e.target.value);
            if (!Number.isFinite(value)) return;
            onProfileChange((p) => ({
              ...p,
              front_overlap_pct: Math.min(85, Math.max(75, value)),
            }));
          }}
          inputProps={{ min: 75, max: 85, step: 1 }}
        />
        <TextField
          variant="filled"
          size="small"
          label="Side overlap (%)"
          type="number"
          value={profile.side_overlap_pct}
          onChange={(e) => {
            const value = Number(e.target.value);
            if (!Number.isFinite(value)) return;
            onProfileChange((p) => ({
              ...p,
              side_overlap_pct: Math.min(75, Math.max(65, value)),
            }));
          }}
          inputProps={{ min: 65, max: 75, step: 1 }}
        />
        <TextField
          variant="filled"
          size="small"
          label={
            <InfoLabel
              label="Speed (m/s)"
              info="Slow flight helps reduce motion blur."
            />
          }
          InputLabelProps={INFO_INPUT_LABEL_PROPS}
          type="number"
          value={profile.speed_mps}
          onChange={(e) => {
            const value = Number(e.target.value);
            if (!Number.isFinite(value)) return;
            onProfileChange((p) => ({
              ...p,
              speed_mps: Math.min(8, Math.max(1, value)),
            }));
          }}
          inputProps={{ min: 1, max: 8, step: 0.1 }}
        />
        <TextField
          variant="filled"
          select
          size="small"
          label="Trigger mode"
          value={profile.trigger_mode}
          onChange={(e) =>
            onProfileChange((p) => ({
              ...p,
              trigger_mode: e.target.value as PhotogrammetryProfile["trigger_mode"],
            }))
          }
        >
          <MenuItem value="distance">Distance-based</MenuItem>
          <MenuItem value="time">Time-based</MenuItem>
        </TextField>
        {profile.trigger_mode === "distance" ? (
          <TextField
            variant="filled"
            size="small"
            label="Trigger distance (m)"
            type="number"
            value={profile.trigger_distance_m}
            onChange={(e) => {
              const value = Number(e.target.value);
              if (!Number.isFinite(value)) return;
              onProfileChange((p) => ({
                ...p,
                trigger_distance_m: Math.min(20, Math.max(0.5, value)),
              }));
            }}
            inputProps={{ min: 0.5, max: 20, step: 0.1 }}
          />
        ) : (
          <TextField
            variant="filled"
            size="small"
            label="Trigger interval (s)"
            type="number"
            value={profile.trigger_interval_s}
            onChange={(e) => {
              const value = Number(e.target.value);
              if (!Number.isFinite(value)) return;
              onProfileChange((p) => ({
                ...p,
                trigger_interval_s: Math.min(10, Math.max(0.2, value)),
              }));
            }}
            inputProps={{ min: 0.2, max: 10, step: 0.1 }}
          />
        )}
        <TextField
          variant="filled"
          select
          size="small"
          label="Accuracy option"
          value={profile.positioning}
          onChange={(e) =>
            onProfileChange((p) => ({
              ...p,
              positioning: e.target.value as PhotogrammetryProfile["positioning"],
            }))
          }
        >
          <MenuItem value="rtk_ppk">RTK/PPK</MenuItem>
          <MenuItem value="standard_gnss">Standard GNSS</MenuItem>
        </TextField>
      </Box>
      <FormControlLabel
        sx={{ mt: 0.5 }}
        control={
          <Switch
            size="small"
            checked={profile.fixed_exposure}
            onChange={(e) =>
              onProfileChange((p) => ({
                ...p,
                fixed_exposure: e.target.checked,
              }))
            }
          />
        }
        label={
          <Typography variant="caption">
            Camera: nadir + fixed exposure (recommended)
          </Typography>
        }
      />
    </Paper>
  );
}
