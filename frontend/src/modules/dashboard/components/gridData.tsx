import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { GridColDef, GridRenderCellParams } from "@mui/x-data-grid";

const renderHeaderTooltip = (label: string, title: string) => () => (
  <Tooltip title={title} arrow>
    <Typography variant="caption" sx={{ fontWeight: 700 }}>
      {label}
    </Typography>
  </Tooltip>
);

export const columns: GridColDef[] = [
  {
    field: "plan",
    headerName: "Field Plan",
    renderHeader: renderHeaderTooltip(
      "Field Plan",
      "Mission or field route name",
    ),
    flex: 1.2,
    minWidth: 180,
  },
  {
    field: "status",
    headerName: "Status",
    renderHeader: renderHeaderTooltip(
      "Status",
      "Latest mission execution state",
    ),
    flex: 0.6,
    minWidth: 100,
    renderCell: (params: GridRenderCellParams) => {
      const label = typeof params.value === "string" ? params.value : "Unknown";
      const value = label.toLowerCase();
      const color =
        value.includes("progress") || value.includes("active")
          ? "success"
          : value.includes("fail")
            ? "error"
            : "default";
      return (
        <Chip label={label} color={color} size="small" variant="outlined" />
      );
    },
  },
  {
    field: "duration",
    headerName: "Duration",
    renderHeader: renderHeaderTooltip(
      "Duration",
      "Elapsed time from launch to completion",
    ),
    headerAlign: "right",
    align: "right",
    flex: 0.7,
    minWidth: 110,
  },
  {
    field: "distance",
    headerName: "Distance",
    renderHeader: renderHeaderTooltip("Distance", "Total route distance flown"),
    headerAlign: "right",
    align: "right",
    flex: 0.7,
    minWidth: 110,
  },
  {
    field: "telemetry_points",
    headerName: "Telemetry",
    renderHeader: renderHeaderTooltip(
      "Telemetry",
      "Number of telemetry samples recorded",
    ),
    headerAlign: "right",
    align: "right",
    flex: 0.7,
    minWidth: 120,
  },
  {
    field: "started_at",
    headerName: "Started",
    renderHeader: renderHeaderTooltip(
      "Started",
      "Local start time for the run",
    ),
    headerAlign: "right",
    align: "right",
    flex: 0.9,
    minWidth: 140,
  },
];
