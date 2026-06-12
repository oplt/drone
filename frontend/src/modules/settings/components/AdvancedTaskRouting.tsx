import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import Grid from "@mui/material/Grid";

import type { LlmProfile, LlmTaskName } from "../api/settingsApi";
import { TASK_LABELS } from "../aiSettingsDefaults";

const TASK_HINTS: Partial<Record<LlmTaskName, string>> = {
  private_patrol: "Local model recommended for property privacy.",
  mission_planning: "Stronger model may improve reasoning.",
  video_summary: "Vision-capable model required when sending images.",
};

type Props = {
  profiles: LlmProfile[];
  taskOverrides: Partial<Record<LlmTaskName, string>>;
  onChange: (overrides: Partial<Record<LlmTaskName, string>>) => void;
};

export function AdvancedTaskRouting({ profiles, taskOverrides, onChange }: Props) {
  const updateOverride = (task: LlmTaskName, profileId: string) => {
    const next = { ...taskOverrides };
    if (profileId) next[task] = profileId;
    else delete next[task];
    onChange(next);
  };

  return (
    <Accordion>
      <AccordionSummary>Advanced Task Routing</AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Default profile is used for every task unless an override is selected.
          </Typography>
          {(Object.keys(TASK_LABELS) as LlmTaskName[]).map((task) => (
            <Grid key={task} container spacing={1.5} alignItems="center">
              <Grid size={{ xs: 12, md: 5 }}>
                <Typography>{TASK_LABELS[task]}</Typography>
                {TASK_HINTS[task] && (
                  <Typography variant="caption" color="text.secondary">
                    {TASK_HINTS[task]}
                  </Typography>
                )}
              </Grid>
              <Grid size={{ xs: 12, md: 7 }}>
                <TextField
                  select
                  fullWidth
                  variant="filled"
                  label="Route"
                  value={taskOverrides[task] ?? ""}
                  onChange={(event) => updateOverride(task, event.target.value)}
                >
                  <MenuItem value="">Use default</MenuItem>
                  {profiles.map((profile) => (
                    <MenuItem key={profile.id} value={profile.id}>
                      {profile.name}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
            </Grid>
          ))}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
