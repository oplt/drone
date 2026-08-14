import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { radius } from "../../../shared/theme/themePrimitives";

export type MissionMapLegendItem = {
  label: string;
  color: string;
};

const DEFAULT_SURVEY_LEGEND: MissionMapLegendItem[] = [
  { label: "Work legs", color: "#2e7d32" },
  { label: "Turn legs", color: "#ed6c02" },
  { label: "Planned route", color: "#1976d2" },
  { label: "Field boundary", color: "#9c27b0" },
];

export function MissionMapLegend({
  items = DEFAULT_SURVEY_LEGEND,
  title = "Map layers",
}: {
  items?: MissionMapLegendItem[];
  title?: string;
}) {
  return (
    <Paper
      variant="mapOverlay"
      elevation={0}
      sx={{
        position: "absolute",
        right: 10,
        bottom: 10,
        zIndex: 1200,
        pointerEvents: "none",
        px: 1.25,
        py: 1,
        borderRadius: radius.sm,
        maxWidth: 220,
      }}
      aria-label={title}
    >
      <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>
        {title}
      </Typography>
      <Stack spacing={0.5}>
        {items.map((item) => (
          <Stack key={item.label} direction="row" spacing={1} alignItems="center">
            <Chip
              size="small"
              sx={{
                width: 12,
                height: 12,
                bgcolor: item.color,
                "& .MuiChip-label": { display: "none" },
              }}
            />
            <Typography variant="caption">{item.label}</Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}
