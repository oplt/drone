import { Slider, Stack, Typography } from "@mui/material";
import type { AgricultureTimelineFlight } from "../types";

export function FlightTimeline({
  flights,
  value,
  onChange,
}: {
  flights: AgricultureTimelineFlight[];
  value: number;
  onChange: (index: number) => void;
}) {
  return (
    <Stack
      component="section"
      aria-labelledby="flight-timeline-heading"
      direction="row"
      spacing={1}
      alignItems="center"
    >
      <Typography id="flight-timeline-heading" variant="caption">
        Flight timeline
      </Typography>
      <Slider
        aria-label="Flight timeline"
        value={value}
        onChange={(_, next) => onChange(next as number)}
        min={0}
        max={Math.max(0, flights.length - 1)}
        step={1}
        marks
        valueLabelDisplay="auto"
        valueLabelFormat={(index) =>
          new Date(
            flights[index]?.created_at ?? Date.now(),
          ).toLocaleDateString()
        }
        sx={{ flex: 1 }}
      />
    </Stack>
  );
}
