import { useId } from "react";
import { useTheme } from "@mui/material/styles";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { SparkLineChart } from "@mui/x-charts/SparkLineChart";
import { areaElementClasses } from "@mui/x-charts/LineChart";
import type { DashboardStatCard } from "../types";

export type StatCardProps = DashboardStatCard;

function AreaGradient({ color, id }: { color: string; id: string }) {
  return (
    <defs>
      <linearGradient id={id} x1="50%" y1="0%" x2="50%" y2="100%">
        <stop offset="0%" stopColor={color} stopOpacity={0.3} />
        <stop offset="100%" stopColor={color} stopOpacity={0} />
      </linearGradient>
    </defs>
  );
}

export default function StatCard({
  title,
  value,
  interval,
  trend,
  data,
  deltaLabel,
  labels,
  tooltip,
}: StatCardProps) {
  const theme = useTheme();
  const gradientId = useId().replace(/:/g, "-");

  const trendColors = {
    up: theme.palette.success.main,
    down: theme.palette.error.main,
    neutral: theme.palette.grey[500],
  };

  const labelColors = {
    up: "success" as const,
    down: "error" as const,
    neutral: "default" as const,
  };

  const color = labelColors[trend];
  const chartColor = trendColors[trend];
  const xLabels =
    labels && labels.length === data.length
      ? labels
      : data.map((_, index) => `${index + 1}`);

  return (
    <Card variant="outlined" sx={{ height: "100%", flexGrow: 1 }}>
      <Stack spacing={2} sx={{ height: "100%" }}>
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="flex-start"
          spacing={2}
        >
          <Stack spacing={0.75}>
            <Tooltip
              title={tooltip ?? ""}
              arrow
              disableHoverListener={!tooltip}
            >
              <Typography component="h2" variant="subtitle2">
                {title}
              </Typography>
            </Tooltip>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              {interval}
            </Typography>
          </Stack>
          {deltaLabel ? (
            <Tooltip title="Change versus previous period" arrow>
              <Chip size="small" color={color} label={deltaLabel} />
            </Tooltip>
          ) : null}
        </Stack>

        <Typography variant="h4" component="p">
          {value}
        </Typography>

        <Box sx={{ width: "100%", minHeight: 68, mt: "auto" }}>
          {data.length > 0 ? (
            <SparkLineChart
              color={chartColor}
              data={data}
              area
              showHighlight
              showTooltip
              xAxis={{
                scaleType: "band",
                data: xLabels,
              }}
              sx={{
                [`& .${areaElementClasses.root}`]: {
                  fill: `url(#area-gradient-${gradientId})`,
                },
              }}
            >
              <AreaGradient
                color={chartColor}
                id={`area-gradient-${gradientId}`}
              />
            </SparkLineChart>
          ) : (
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              No data yet
            </Typography>
          )}
        </Box>
      </Stack>
    </Card>
  );
}
