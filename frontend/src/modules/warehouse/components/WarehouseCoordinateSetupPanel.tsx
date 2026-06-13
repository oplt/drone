import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import DeleteRoundedIcon from "@mui/icons-material/DeleteRounded";
import PlaceRoundedIcon from "@mui/icons-material/PlaceRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import {
  createWarehouseScanTarget,
  deleteWarehouseScanTarget,
  type WarehouseScanTarget,
} from "../api/warehouseInspectionApi";
import type { WarehouseMapPlacementPanelProps } from "../hooks/useWarehouseMapPlacement";
import {
  formatMapPoint,
  SHELF_FACE_OPTIONS,
  shelfNormalFromFacing,
  WAREHOUSE_MAP_FRAME_ID,
} from "../utils/warehouseMapPlacement";

type TargetDraft = {
  aisle_code: string;
  rack_code: string;
  shelf_level: string;
  bin_code: string;
  sku: string;
  barcode: string;
  product_name: string;
  hover_time_s: string;
};

const emptyDraft: TargetDraft = {
  aisle_code: "",
  rack_code: "",
  shelf_level: "",
  bin_code: "",
  sku: "",
  barcode: "",
  product_name: "",
  hover_time_s: "3",
};

const parseNumber = (label: string, value: string): number => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be a finite number.`);
  }
  return parsed;
};

export function WarehouseCoordinateSetupPanel({
  warehouseMapId,
  token,
  onError,
  mapPlacement,
}: {
  warehouseMapId: number | null;
  token?: string | null;
  onError: (message: string) => void;
  mapPlacement: WarehouseMapPlacementPanelProps;
}) {
  const [draft, setDraft] = useState<TargetDraft>(emptyDraft);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const { targets, targetsLoading, refreshTargets } = mapPlacement;

  useEffect(() => {
    if (!mapPlacement.draftTarget) return;
    setDraft((current) => ({
      ...current,
      shelf_level:
        current.shelf_level.trim() ||
        String(Math.max(1, Math.round(mapPlacement.draftTarget!.z_m))),
    }));
  }, [mapPlacement.draftTarget]);

  const pickedSummary = useMemo(() => {
    if (!mapPlacement.draftTarget) return null;
    const targetText = formatMapPoint(mapPlacement.draftTarget);
    const scanText = mapPlacement.draftScanPose
      ? `${mapPlacement.draftScanPose.x_m.toFixed(2)}, ${mapPlacement.draftScanPose.y_m.toFixed(2)}, ${mapPlacement.draftScanPose.z_m.toFixed(2)} @ ${mapPlacement.draftScanPose.yaw_deg ?? 0}°`
      : "computing…";
    return { targetText, scanText };
  }, [mapPlacement.draftScanPose, mapPlacement.draftTarget]);

  const handleCreate = useCallback(async () => {
    if (warehouseMapId == null) {
      onError("Select a warehouse map first.");
      return;
    }
    if (!mapPlacement.draftTarget || !mapPlacement.draftScanPose) {
      onError("Pick a bin location on the 3D map first.");
      return;
    }
    if (!draft.aisle_code.trim()) {
      onError("Aisle code is required.");
      return;
    }

    try {
      setSaving(true);
      const shelfLevel = draft.shelf_level.trim()
        ? Number.parseInt(draft.shelf_level, 10)
        : null;
      await createWarehouseScanTarget(
        warehouseMapId,
        {
          aisle_code: draft.aisle_code.trim(),
          rack_code: draft.rack_code.trim() || null,
          shelf_level: Number.isFinite(shelfLevel) ? shelfLevel : null,
          bin_code: draft.bin_code.trim() || null,
          sku: draft.sku.trim() || null,
          barcode: draft.barcode.trim() || null,
          product_name: draft.product_name.trim() || null,
          target_point_local_json: {
            frame_id: WAREHOUSE_MAP_FRAME_ID,
            x_m: mapPlacement.draftTarget.x_m,
            y_m: mapPlacement.draftTarget.y_m,
            z_m: mapPlacement.draftTarget.z_m,
          },
          scan_pose_local_json: {
            frame_id: WAREHOUSE_MAP_FRAME_ID,
            x_m: mapPlacement.draftScanPose.x_m,
            y_m: mapPlacement.draftScanPose.y_m,
            z_m: mapPlacement.draftScanPose.z_m,
            yaw_deg: mapPlacement.draftScanPose.yaw_deg ?? 0,
          },
          shelf_normal_local_json: shelfNormalFromFacing(mapPlacement.shelfFacing),
          standoff_m: mapPlacement.standoffM,
          hover_time_s: parseNumber("Hover time", draft.hover_time_s),
        },
        token,
      );
      setDraft(emptyDraft);
      mapPlacement.clearDraft();
      setMessage("Scan target saved. Markers updated on the 3D map.");
      await refreshTargets();
    } catch (error) {
      onError(error instanceof Error ? error.message : "Scan target could not be saved.");
    } finally {
      setSaving(false);
    }
  }, [draft, mapPlacement, onError, refreshTargets, token, warehouseMapId]);

  const handleDelete = useCallback(
    async (targetId: number) => {
      if (warehouseMapId == null) return;
      try {
        await deleteWarehouseScanTarget(warehouseMapId, targetId, token);
        setMessage("Scan target archived.");
        await refreshTargets();
      } catch (error) {
        onError(error instanceof Error ? error.message : "Scan target could not be deleted.");
      }
    },
    [onError, refreshTargets, token, warehouseMapId],
  );

  if (warehouseMapId == null) {
    return (
      <Alert severity="info">
        Select a warehouse map in Setup to place bin coordinates on the 3D map.
      </Alert>
    );
  }

  return (
    <Stack spacing={2}>
      {message ? <Alert severity="success">{message}</Alert> : null}
      <Typography variant="body2" color="text.secondary">
        Enable pick mode, click a bin on the 3D map above, label aisle/rack/bin, then save.
        The drone flies to the computed scan pose (cyan cone), not into the shelf.
      </Typography>

      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={1}
        alignItems={{ md: "center" }}
        flexWrap="wrap"
      >
        <FormControlLabel
          control={
            <Switch
              checked={mapPlacement.pickMode}
              onChange={(event) => mapPlacement.setPickMode(event.target.checked)}
            />
          }
          label="Pick on 3D map"
        />
        <TextField
          select
          size="small"
          label="Shelf faces"
          value={mapPlacement.shelfFacing}
          onChange={(event) => mapPlacement.setShelfFacing(event.target.value)}
          sx={{ minWidth: 220 }}
        >
          {SHELF_FACE_OPTIONS.map((option) => (
            <MenuItem key={option.id} value={option.id}>
              {option.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          type="number"
          label="Pick height Z (m)"
          value={mapPlacement.placementZ}
          onChange={(event) => mapPlacement.setPlacementZ(Number(event.target.value))}
          inputProps={{ step: 0.1, min: 0, max: 12 }}
          sx={{ width: 140 }}
        />
        <TextField
          size="small"
          type="number"
          label="Standoff (m)"
          value={mapPlacement.standoffM}
          onChange={(event) => mapPlacement.setStandoffM(Number(event.target.value))}
          inputProps={{ step: 0.1, min: 0.3, max: 5 }}
          sx={{ width: 120 }}
        />
      </Stack>

      {pickedSummary ? (
        <Alert severity="info" icon={<PlaceRoundedIcon fontSize="inherit" />}>
          Target: {pickedSummary.targetText} · Scan pose: {pickedSummary.scanText}
        </Alert>
      ) : mapPlacement.pickMode ? (
        <Alert severity="warning">Click the warehouse 3D map to place the bin target.</Alert>
      ) : null}

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "repeat(4, minmax(0, 1fr))" },
          gap: 1,
        }}
      >
        {(
          [
            ["aisle_code", "Aisle *"],
            ["rack_code", "Rack"],
            ["shelf_level", "Shelf level"],
            ["bin_code", "Bin"],
            ["sku", "SKU"],
            ["barcode", "Barcode"],
            ["product_name", "Product"],
            ["hover_time_s", "Hover (s)"],
          ] as const
        ).map(([key, label]) => (
          <TextField
            key={key}
            size="small"
            label={label}
            value={draft[key]}
            onChange={(event) =>
              setDraft((current) => ({ ...current, [key]: event.target.value }))
            }
          />
        ))}
      </Box>
      <Stack direction="row" spacing={1} flexWrap="wrap">
        <Button
          variant="contained"
          size="small"
          startIcon={<AddRoundedIcon />}
          onClick={() => void handleCreate()}
          disabled={
            saving ||
            !mapPlacement.draftTarget ||
            !mapPlacement.draftScanPose
          }
        >
          Save Target
        </Button>
        <Button
          variant="outlined"
          size="small"
          onClick={() => mapPlacement.clearDraft()}
          disabled={!mapPlacement.draftTarget}
        >
          Clear Pick
        </Button>
        <Button
          variant="outlined"
          size="small"
          startIcon={<RefreshRoundedIcon />}
          onClick={() => void refreshTargets()}
          disabled={targetsLoading}
        >
          Refresh
        </Button>
      </Stack>

      <Table size="small" aria-label="warehouse scan targets">
        <TableHead>
          <TableRow>
            <TableCell>Location</TableCell>
            <TableCell>Product</TableCell>
            <TableCell>Target Point</TableCell>
            <TableCell>Scan Pose</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {targets.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5}>
                <Typography variant="body2" color="text.secondary">
                  No saved targets yet. Pick a location on the map and save.
                </Typography>
              </TableCell>
            </TableRow>
          ) : (
            targets.map((target: WarehouseScanTarget) => (
              <TableRow key={target.id}>
                <TableCell>
                  {target.aisle_code} {target.rack_code ?? ""} {target.bin_code ?? ""}
                </TableCell>
                <TableCell>
                  {target.sku ?? target.barcode ?? target.product_name ?? "-"}
                </TableCell>
                <TableCell>
                  {target.target_point_local_json.x_m.toFixed(1)},{" "}
                  {target.target_point_local_json.y_m.toFixed(1)},{" "}
                  {target.target_point_local_json.z_m.toFixed(1)}
                </TableCell>
                <TableCell>
                  {target.scan_pose_local_json.x_m.toFixed(1)},{" "}
                  {target.scan_pose_local_json.y_m.toFixed(1)},{" "}
                  {target.scan_pose_local_json.z_m.toFixed(1)} @{" "}
                  {target.scan_pose_local_json.yaw_deg ?? 0}°
                </TableCell>
                <TableCell align="right">
                  <Button
                    size="small"
                    color="error"
                    startIcon={<DeleteRoundedIcon />}
                    onClick={() => void handleDelete(target.id)}
                  >
                    Archive
                  </Button>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </Stack>
  );
}
