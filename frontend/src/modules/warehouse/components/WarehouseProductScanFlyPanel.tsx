import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import PlayArrowRoundedIcon from "@mui/icons-material/PlayArrowRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import {
  createWarehouseInspectionMission,
  approveWarehouseInspectionMission,
  runWarehouseInspectionMissionMock,
  type WarehouseInspectionMission,
  type WarehouseInspectionResult,
  type WarehouseScanTarget,
} from "../api/warehouseInspectionApi";
import type { WarehouseMapPlacementPanelProps } from "../hooks/useWarehouseMapPlacement";

export function WarehouseProductScanFlyPanel({
  warehouseMapId,
  token,
  onError,
  mapPlacement,
}: {
  warehouseMapId: number | null;
  token?: string | null;
  onError: (message: string) => void;
  mapPlacement: Pick<
    WarehouseMapPlacementPanelProps,
    "targets" | "targetsLoading" | "refreshTargets"
  >;
}) {
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [results, setResults] = useState<WarehouseInspectionResult[]>([]);
  const [preview, setPreview] = useState<WarehouseInspectionMission | null>(
    null,
  );
  const [scanMode, setScanMode] = useState<
    "barcode" | "product_photo" | "visual_check" | "mixed"
  >("barcode");

  const { targets, targetsLoading, refreshTargets } = mapPlacement;

  useEffect(() => {
    setSelectedIds((current) =>
      current.filter((id) => targets.some((row) => row.id === id)),
    );
  }, [targets]);

  const handleRunMission = useCallback(async () => {
    if (warehouseMapId == null || selectedIds.length === 0) {
      onError("Select at least one scan target.");
      return;
    }
    setRunning(true);
    try {
      const mission = await createWarehouseInspectionMission(
        {
          warehouse_map_id: warehouseMapId,
          name: "Warehouse Product Scan",
          target_ids: selectedIds,
          scan_mode: scanMode,
          optimize_order: true,
          return_to_dock: true,
        },
        token,
      );
      setPreview(mission);
      setResults([]);
      setMessage(
        `Mission #${mission.id} preview ready with ${mission.waypoints.length} semantic stages.`,
      );
    } catch (error) {
      onError(
        error instanceof Error
          ? error.message
          : "Inspection mission could not be created.",
      );
    } finally {
      setRunning(false);
    }
  }, [onError, scanMode, selectedIds, token, warehouseMapId]);

  const handleApproveAndRun = useCallback(async () => {
    if (!preview) return;
    setRunning(true);
    try {
      const approved = await approveWarehouseInspectionMission(preview, token);
      setPreview(approved);
      setResults(await runWarehouseInspectionMissionMock(approved.id, token));
      setMessage(`Mission #${approved.id} approved and executed.`);
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Mission execution failed.",
      );
    } finally {
      setRunning(false);
    }
  }, [onError, preview, token]);

  if (warehouseMapId == null) {
    return (
      <Alert severity="info">
        Select a warehouse map in Setup before planning a product scan flight.
      </Alert>
    );
  }

  return (
    <Stack spacing={2}>
      {message ? <Alert severity="success">{message}</Alert> : null}
      <Typography variant="body2" color="text.secondary">
        Choose saved bin targets, set scan mode, then create a warehouse product
        scan mission. Targets are defined under Coordinate Setup on the 3D map.
      </Typography>

      <Stack direction="row" spacing={1} flexWrap="wrap">
        <Button
          variant="outlined"
          size="small"
          startIcon={<RefreshRoundedIcon />}
          onClick={() => void refreshTargets()}
          disabled={targetsLoading}
        >
          Refresh targets
        </Button>
      </Stack>

      <Table size="small" aria-label="product scan mission targets">
        <TableHead>
          <TableRow>
            <TableCell padding="checkbox" />
            <TableCell>Location</TableCell>
            <TableCell>Product</TableCell>
            <TableCell>Scan Pose</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {targets.length === 0 ? (
            <TableRow>
              <TableCell colSpan={4}>
                <Typography variant="body2" color="text.secondary">
                  No targets saved. Add coordinates on the 3D map Coordinate
                  Setup tab.
                </Typography>
              </TableCell>
            </TableRow>
          ) : (
            targets.map((target: WarehouseScanTarget) => (
              <TableRow
                key={target.id}
                selected={selectedIds.includes(target.id)}
              >
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={selectedIds.includes(target.id)}
                    onChange={(event) =>
                      setSelectedIds((current) =>
                        event.target.checked
                          ? [...current, target.id]
                          : current.filter((id) => id !== target.id),
                      )
                    }
                    inputProps={{ "aria-label": `Select target ${target.id}` }}
                  />
                </TableCell>
                <TableCell>
                  {target.aisle_code} {target.rack_code ?? ""}{" "}
                  {target.bin_code ?? ""}
                </TableCell>
                <TableCell>
                  {target.sku ?? target.barcode ?? target.product_name ?? "-"}
                </TableCell>
                <TableCell>
                  {target.scan_pose_local_json.x_m.toFixed(1)},{" "}
                  {target.scan_pose_local_json.y_m.toFixed(1)},{" "}
                  {target.scan_pose_local_json.z_m.toFixed(1)} @{" "}
                  {target.scan_pose_local_json.yaw_deg ?? 0}°
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={1}
        alignItems={{ md: "center" }}
      >
        <TextField
          select
          size="small"
          label="Scan Mode"
          value={scanMode}
          onChange={(event) =>
            setScanMode(event.target.value as typeof scanMode)
          }
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="barcode">Barcode</MenuItem>
          <MenuItem value="product_photo">Product Photo</MenuItem>
          <MenuItem value="visual_check">Visual Check</MenuItem>
          <MenuItem value="mixed">Mixed</MenuItem>
        </TextField>
        <FormControlLabel
          control={<Checkbox checked readOnly />}
          label="Optimize order"
        />
        <Button
          variant="contained"
          startIcon={<PlayArrowRoundedIcon />}
          onClick={() => void handleRunMission()}
          disabled={running || selectedIds.length === 0}
        >
          Create Mission Preview
        </Button>
      </Stack>

      {preview && preview.approval_status === "pending" ? (
        <Alert
          severity="warning"
          action={
            <Button
              color="inherit"
              disabled={running}
              onClick={() => void handleApproveAndRun()}
            >
              Approve and execute
            </Button>
          }
        >
          Review mission #{preview.id}: {preview.target_ids.length} targets,{" "}
          {preview.waypoints.length} approach/hover/scan/exit stages. Execution
          revalidates frame, layout, map artifacts, TF, and runtime policy.
        </Alert>
      ) : null}

      {results.length > 0 ? (
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            p: 1,
          }}
        >
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
            Inspection Results
          </Typography>
          {results.map((result) => (
            <Typography key={result.id} variant="body2">
              Target #{result.target_id}: {result.status}
              {result.detected_barcode ? ` (${result.detected_barcode})` : ""}
            </Typography>
          ))}
        </Box>
      ) : null}
    </Stack>
  );
}
