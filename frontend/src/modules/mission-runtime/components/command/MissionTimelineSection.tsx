import { Alert, Box, Chip, Stack, Typography } from "@mui/material";
import type { MissionLifecycleState } from "../../types";
import type { TimelineEntry } from "../../lib/missionTimeline";
import { formatTs, stateChipColor } from "./formatters";

export function MissionTimelineSection({
  recentTimeline,
  timelineError,
}: {
  recentTimeline: TimelineEntry[];
  timelineError: string | null;
}) {
  return (
    <Box sx={{ pt: 0.5 }}>
      <Typography
        variant="caption"
        sx={{ display: "block", mb: 0.6, letterSpacing: 0.6, fontWeight: 700 }}
      >
        MISSION TIMELINE
      </Typography>
      {timelineError && <Alert severity="warning">{timelineError}</Alert>}
      {recentTimeline.length === 0 ? (
        <Typography variant="caption" color="text.secondary">
          Timeline entries will appear once the mission starts changing state.
        </Typography>
      ) : (
        <Stack spacing={0.9}>
          {recentTimeline.map((entry) => (
            <Box
              key={entry.key}
              sx={{
                px: 1.1,
                py: 0.8,
                borderRadius: 1.5,
                border: "1px solid",
                borderColor: "divider",
                backgroundColor: "background.paper",
              }}
            >
              <Stack direction="row" justifyContent="space-between" spacing={1}>
                <Stack spacing={0.3}>
                  <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
                    <Chip
                      size="small"
                      label={entry.label}
                      color={
                        entry.kind === "transition"
                          ? stateChipColor((entry.state as MissionLifecycleState | null) ?? null)
                          : "default"
                      }
                      variant={entry.kind === "transition" ? "filled" : "outlined"}
                    />
                    {entry.state && (
                      <Typography variant="caption" color="text.secondary">
                        {entry.state}
                      </Typography>
                    )}
                  </Stack>
                  <Typography variant="caption" color="text.secondary">
                    {entry.detail}
                  </Typography>
                </Stack>
                <Typography
                  variant="caption"
                  sx={{
                    fontFamily: "monospace",
                    color: "text.secondary",
                    textAlign: "right",
                  }}
                >
                  {formatTs(entry.occurredAt)}
                </Typography>
              </Stack>
            </Box>
          ))}
        </Stack>
      )}
    </Box>
  );
}
