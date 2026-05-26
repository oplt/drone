import { Card, CardContent, Chip, Stack, Typography } from "@mui/material";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import type { LiveSavedDetection } from "../types";

const columns: GridColDef<LiveSavedDetection>[] = [
  {
    field: "created_at",
    headerName: "Observed",
    minWidth: 185,
    valueFormatter: (value) => new Date(String(value)).toLocaleString(),
  },
  { field: "flight_id", headerName: "Flight", width: 90 },
  {
    field: "label",
    headerName: "Class",
    minWidth: 130,
    flex: 1,
    renderCell: ({ value }) => <Chip size="small" label={value} color="success" />,
  },
  {
    field: "confidence",
    headerName: "Confidence",
    width: 120,
    valueFormatter: (value) => `${Math.round(Number(value) * 100)}%`,
  },
  { field: "model_name", headerName: "Model", minWidth: 130 },
];

type Props = {
  rows: LiveSavedDetection[];
  loading: boolean;
};

export function LiveDetectionLog({ rows, loading }: Props) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 1 }}>
          <Typography variant="h6">Live survey camera detections</Typography>
          <Typography variant="caption" color="text.secondary">
            Saved while object detection is enabled during an active mission
          </Typography>
        </Stack>
        <DataGrid
          rows={rows}
          columns={columns}
          getRowId={(row) => row.id}
          loading={loading}
          density="compact"
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
          disableRowSelectionOnClick
          sx={{ minHeight: 270 }}
        />
      </CardContent>
    </Card>
  );
}
