import { useState } from "react";
import { Box, Card, CardContent, Chip, Tab, Tabs, Typography } from "@mui/material";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import type { LiveSavedDetection, VideoDetection } from "../types";
import { LiveDetectionLog } from "./LiveDetectionLog";

const jobColumns: GridColDef<VideoDetection>[] = [
  {
    field: "timestamp_seconds",
    headerName: "Time",
    width: 90,
    valueFormatter: (value) => `${Number(value).toFixed(1)}s`,
  },
  {
    field: "label",
    headerName: "Class",
    flex: 1,
    minWidth: 140,
    renderCell: ({ value }) => <Chip size="small" label={value} />,
  },
  {
    field: "confidence",
    headerName: "Confidence",
    width: 120,
    valueFormatter: (value) => `${(Number(value) * 100).toFixed(0)}%`,
  },
  { field: "frame_index", headerName: "Frame", width: 100 },
  {
    field: "gps",
    headerName: "GPS",
    width: 190,
    valueGetter: (_value, row) =>
      row.lat != null && row.lon != null
        ? `${row.lat.toFixed(6)}, ${row.lon.toFixed(6)}`
        : "No location",
  },
];

type DetectionLogsTabsProps = {
  liveRows: LiveSavedDetection[];
  liveLoading: boolean;
  jobRows: VideoDetection[];
  jobLoading: boolean;
  onJobRowSelect: (detection: VideoDetection) => void;
};

export function DetectionLogsTabs({
  liveRows,
  liveLoading,
  jobRows,
  jobLoading,
  onJobRowSelect,
}: DetectionLogsTabsProps) {
  const [tab, setTab] = useState<"live" | "job">("live");

  return (
    <Card variant="outlined">
      <CardContent sx={{ pb: 1 }}>
        <Tabs
          value={tab}
          onChange={(_event, value: "live" | "job") => setTab(value)}
          sx={{ mb: 1, borderBottom: 1, borderColor: "divider" }}
        >
          <Tab value="live" label="Live survey camera detections" />
          <Tab value="job" label="Detection log" />
        </Tabs>

        {tab === "live" ? (
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Saved while object detection is enabled during an active mission.
            </Typography>
            <LiveDetectionLog rows={liveRows} loading={liveLoading} embedded />
          </Box>
        ) : (
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Detections from the uploaded video analysis job.
            </Typography>
            <DataGrid
              rows={jobRows}
              columns={jobColumns}
              loading={jobLoading}
              density="compact"
              pageSizeOptions={[10, 25, 50]}
              initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
              onRowClick={({ row }) => onJobRowSelect(row)}
              disableRowSelectionOnClick
              sx={{ minHeight: 320 }}
            />
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
