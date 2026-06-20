import {
  lazy,
  Suspense,
  type ComponentProps,
  type RefObject,
} from "react";
import { CircularProgress, Paper, Stack, Typography } from "@mui/material";
import { WarehouseDashboardCard } from "./WarehouseDashboardUi";
import { WarehouseScanResultsSelector } from "./WarehouseScanResultsSelector";

const WarehouseLiveVoxelMapViewer = lazy(async () => {
  const module = await import("./WarehouseLiveVoxelMapViewer");
  return { default: module.WarehouseLiveVoxelMapViewer };
});

type WarehouseViewerSectionProps = {
  sectionRef: RefObject<HTMLDivElement | null>;
  selectorProps: ComponentProps<typeof WarehouseScanResultsSelector>;
  showViewer: boolean;
  replayMode: boolean;
  viewerProps: ComponentProps<typeof WarehouseLiveVoxelMapViewer>;
};

export function WarehouseViewerSection({
  sectionRef,
  selectorProps,
  showViewer,
  replayMode,
  viewerProps,
}: WarehouseViewerSectionProps) {
  return (
    <Stack spacing={1} ref={sectionRef} id="warehouse-3d-map-viewer">
      <Paper
        variant="outlined"
        sx={{
          p: 1.5,
          borderRadius: 1,
          borderColor: "divider",
          backgroundColor: "background.paper",
        }}
      >
        <Stack spacing={1}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Previous Scan Results
          </Typography>
          <WarehouseScanResultsSelector {...selectorProps} />
        </Stack>
      </Paper>

      {showViewer ? (
        <WarehouseDashboardCard
          title="Warehouse 3D Map"
          subtitle={
            replayMode
              ? "Stored point-cloud replay for the selected scan"
              : "Live indoor point cloud from nvblox and lidar"
          }
        >
          <Suspense
            fallback={
              <Stack alignItems="center" justifyContent="center" sx={{ minHeight: 360 }}>
                <CircularProgress size={28} />
              </Stack>
            }
          >
            <WarehouseLiveVoxelMapViewer {...viewerProps} />
          </Suspense>
        </WarehouseDashboardCard>
      ) : null}
    </Stack>
  );
}
