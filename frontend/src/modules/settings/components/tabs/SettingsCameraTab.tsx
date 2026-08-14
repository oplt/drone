import { FormControlLabel, Stack, Switch, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid";
import { SecretField } from "../SecretField";
import type { SettingsTabPanelProps } from "../settingsTabProps";

export function SettingsCameraTab({ doc, update }: SettingsTabPanelProps) {
  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 6 }}>
        <Typography variant="h6" gutterBottom>
          Drone Camera Parameters
        </Typography>
        <Stack spacing={3}>
          <SecretField
            fullWidth
            label="Camera Source"
            value={doc.camera?.drone_video_source}
            onChange={(e) => update("camera", "drone_video_source", e.target.value)}
          />
          <SecretField
            fullWidth
            label="Sim UDP Camera Source"
            value={doc.camera?.drone_video_source_gazebo}
            onChange={(e) => update("camera", "drone_video_source_gazebo", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Width"
            type="number"
            value={doc.camera?.drone_video_width}
            onChange={(e) => update("camera", "drone_video_width", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Height"
            type="number"
            value={doc.camera?.drone_video_height}
            onChange={(e) => update("camera", "drone_video_height", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="FPS"
            type="number"
            value={doc.camera?.drone_video_fps}
            onChange={(e) => update("camera", "drone_video_fps", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Timeout"
            type="number"
            value={doc.camera?.drone_video_timeout}
            onChange={(e) => update("camera", "drone_video_timeout", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Recording Save Path"
            value={doc.camera?.drone_video_save_path}
            onChange={(e) => update("camera", "drone_video_save_path", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Fallback"
            value={doc.camera?.drone_video_fallback}
            onChange={(e) => update("camera", "drone_video_fallback", e.target.value)}
          />
          <Stack direction="row" spacing={25}>
            <FormControlLabel
              control={
                <Switch
                  checked={doc.camera?.drone_video_enabled}
                  onChange={(e) => update("camera", "drone_video_enabled", e.target.checked)}
                />
              }
              label="Enable Stream"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={doc.camera?.drone_video_save_stream}
                  onChange={(e) =>
                    update("camera", "drone_video_save_stream", e.target.checked)
                  }
                />
              }
              label="Save Stream"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={doc.camera?.drone_video_use_gazebo}
                  onChange={(e) =>
                    update("camera", "drone_video_use_gazebo", e.target.checked)
                  }
                />
              }
              label="Use sim transport video"
            />
          </Stack>
        </Stack>
      </Grid>
    </Grid>
  );
}
