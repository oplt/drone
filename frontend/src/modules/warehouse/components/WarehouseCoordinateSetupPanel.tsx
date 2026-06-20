import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
  CircularProgress,
} from "@mui/material";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import AutoFixHighRoundedIcon from "@mui/icons-material/AutoFixHighRounded";
import DeleteRoundedIcon from "@mui/icons-material/DeleteRounded";
import PlaceRoundedIcon from "@mui/icons-material/PlaceRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import {
  createWarehouseScanTarget,
  deleteWarehouseScanTarget,
  listWarehouseScanTargets,
  type WarehouseScanTarget,
  type WarehouseStructureExtractParams,
  type WarehouseStructureResponse,
} from "../api/warehouseInspectionApi";
import type { WarehouseMapPlacementPanelProps } from "../hooks/useWarehouseMapPlacement";
import {
  formatMapPoint,
  SHELF_FACE_OPTIONS,
  shelfNormalFromFacing,
  WAREHOUSE_MAP_FRAME_ID,
} from "../utils/warehouseMapPlacement";
import {
  describeStructureQualityReasons,
  structureNeedsReviewMessage,
} from "../utils/structureQualityCopy";
import { AskAgentPanel } from "../../agents/components/AskAgentPanel";

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

const TABLE_PAGE_SIZE = 50;

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
  structure = null,
  extractionStatus = "not_started",
  autoDetecting = false,
  structureLoading = false,
  structureError = null,
  onAutoDetect,
}: {
  warehouseMapId: number | null;
  token?: string | null;
  onError: (message: string) => void;
  mapPlacement: WarehouseMapPlacementPanelProps;
  structure?: WarehouseStructureResponse | null;
  extractionStatus?: WarehouseStructureResponse["status"];
  autoDetecting?: boolean;
  structureLoading?: boolean;
  structureError?: string | null;
  onAutoDetect?: (params?: WarehouseStructureExtractParams) => Promise<void>;
}) {
  const [draft, setDraft] = useState<TargetDraft>(emptyDraft);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [binPitch, setBinPitch] = useState("0.9");
  const [tablePage, setTablePage] = useState(0);
  const [tableRows, setTableRows] = useState<WarehouseScanTarget[]>([]);
  const [tableTotal, setTableTotal] = useState(0);
  const [tableLoading, setTableLoading] = useState(false);

  const { targetsLoading, refreshTargets } = mapPlacement;
  const quality = structure?.summary.quality;
  const qualityStatus = structure?.quality_status ?? quality?.status ?? structure?.status;
  const qualityReasons = structure?.quality_reasons?.length
    ? structure.quality_reasons
    : quality?.reasons ?? [];
  const readableQualityReasons = describeStructureQualityReasons(qualityReasons);
  const activeTargetCount =
    structure?.active_target_count ?? quality?.active_target_count ?? structure?.target_count ?? 0;

  useEffect(() => {
    setSelectedIds((current) =>
      current.filter((id) => tableRows.some((row) => row.id === id)),
    );
  }, [tableRows]);

  const loadTablePage = useCallback(async () => {
    if (warehouseMapId == null) {
      setTableRows([]);
      setTableTotal(0);
      return;
    }
    setTableLoading(true);
    try {
      const page = await listWarehouseScanTargets(warehouseMapId, token, {
        limit: TABLE_PAGE_SIZE,
        offset: tablePage * TABLE_PAGE_SIZE,
      });
      setTableRows(page.items);
      setTableTotal(page.total);
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Scan targets could not be loaded.",
      );
    } finally {
      setTableLoading(false);
    }
  }, [onError, tablePage, token, warehouseMapId]);

  useEffect(() => {
    void loadTablePage();
  }, [loadTablePage]);

  const allSelected =
    tableRows.length > 0 && tableRows.every((row) => selectedIds.includes(row.id));
  const someSelected =
    selectedIds.length > 0 &&
    tableRows.some((row) => selectedIds.includes(row.id)) &&
    !allSelected;

  const handleAutoDetect = useCallback(async () => {
    if (warehouseMapId == null || !onAutoDetect) {
      onError("Select a warehouse map first.");
      return;
    }
    try {
      const pitch = Number(binPitch);
      await onAutoDetect(
        Number.isFinite(pitch) && pitch > 0 ? { bin_pitch_m: pitch } : {},
      );
      setMessage("Structure detected. Auto-generated targets loaded below.");
      await refreshTargets();
      await loadTablePage();
    } catch (error) {
      onError(
        error instanceof Error
          ? error.message
          : "Automatic structure detection failed.",
      );
    }
  }, [binPitch, loadTablePage, onAutoDetect, onError, refreshTargets, warehouseMapId]);

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
      await loadTablePage();
    } catch (error) {
      onError(error instanceof Error ? error.message : "Scan target could not be saved.");
    } finally {
      setSaving(false);
    }
  }, [draft, loadTablePage, mapPlacement, onError, refreshTargets, token, warehouseMapId]);

  const handleDelete = useCallback(
    async (targetId: number) => {
      if (warehouseMapId == null) return;
      try {
        await deleteWarehouseScanTarget(warehouseMapId, targetId, token);
        setSelectedIds((current) => current.filter((id) => id !== targetId));
        setMessage("Scan target archived.");
        await refreshTargets();
        await loadTablePage();
      } catch (error) {
        onError(error instanceof Error ? error.message : "Scan target could not be deleted.");
      }
    },
    [loadTablePage, onError, refreshTargets, token, warehouseMapId],
  );

  const handleDeleteSelected = useCallback(async () => {
    if (warehouseMapId == null || selectedIds.length === 0) return;
    const count = selectedIds.length;
    try {
      setDeleting(true);
      await Promise.all(
        selectedIds.map((targetId) =>
          deleteWarehouseScanTarget(warehouseMapId, targetId, token),
        ),
      );
      setSelectedIds([]);
      setMessage(
        count === 1 ? "Scan target archived." : `${count} scan targets archived.`,
      );
      await refreshTargets();
      await loadTablePage();
    } catch (error) {
      onError(
        error instanceof Error
          ? error.message
          : "Selected scan targets could not be deleted.",
      );
    } finally {
      setDeleting(false);
    }
  }, [loadTablePage, onError, refreshTargets, selectedIds, token, warehouseMapId]);

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

      {structureLoading ? (
        <Alert severity="info" icon={<CircularProgress size={16} />}>
          Loading structure status…
        </Alert>
      ) : null}

      {onAutoDetect ? (
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            p: 1.5,
          }}
        >
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
            Auto-detect warehouse plan
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Analyze the 3D map to find aisles, racks, shelves and bins and
            generate scan targets automatically. Cyan dashed lines are aisles,
            purple wireframes are racks on the map above. Re-run any time with a
            different bin pitch.
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <TextField
              size="small"
              type="number"
              label="Bin pitch (m)"
              value={binPitch}
              onChange={(event) => setBinPitch(event.target.value)}
              inputProps={{ step: 0.1, min: 0.2, max: 5 }}
              sx={{ width: 140 }}
            />
            <Button
              variant="contained"
              size="small"
              startIcon={<AutoFixHighRoundedIcon />}
              onClick={() => void handleAutoDetect()}
              disabled={autoDetecting}
            >
              {autoDetecting ? "Detecting…" : "Auto-detect structure"}
            </Button>
            {structure ? (
              <Typography variant="caption" color="text.secondary">
                {structure.summary.counts?.aisles ?? 0} aisles ·{" "}
                {structure.summary.counts?.racks ?? 0} racks ·{" "}
                {activeTargetCount}/{structure.target_count} active targets
                {quality?.confidence != null
                  ? ` · ${Math.round(quality.confidence * 100)}% confidence`
                  : ""}
                {structure.generated_at
                  ? ` · ${new Date(structure.generated_at).toLocaleString()}`
                  : ""}
              </Typography>
            ) : null}
          </Stack>
          {structureError ? (
            <Alert severity="warning" sx={{ mt: 1, py: 0.25 }}>
              {structureError}
            </Alert>
          ) : null}
          {!autoDetecting && extractionStatus === "queued" ? (
            <Alert severity="info" sx={{ mt: 1, py: 0.25 }}>
              Structure extraction is queued in the warehouse-mapping worker.
            </Alert>
          ) : null}
          {!autoDetecting && extractionStatus === "running" ? (
            <Alert severity="info" sx={{ mt: 1, py: 0.25 }}>
              Structure extraction is running. Aisle and rack overlays will appear when it finishes.
            </Alert>
          ) : null}
          {!autoDetecting && qualityStatus === "needs_review" ? (
            <Alert severity="warning" sx={{ mt: 1, py: 0.25 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Generated targets stayed inactive.
              </Typography>
              <Typography variant="body2">
                {structureNeedsReviewMessage(qualityReasons)}
              </Typography>
              {readableQualityReasons.length ? (
                <Typography variant="caption" color="text.secondary">
                  Check the scan quality: {readableQualityReasons.join("; ")}.
                </Typography>
              ) : null}
            </Alert>
          ) : null}
          {!autoDetecting && extractionStatus === "failed" ? (
            <Alert severity="error" sx={{ mt: 1, py: 0.25 }}>
              Structure extraction failed. Restart the stack with `make warehouse`, then try again.
            </Alert>
          ) : null}
        </Box>
      ) : null}

      {warehouseMapId != null ? (
        <AskAgentPanel
          agentId="warehouse_scan"
          title="Ask about this map"
          basePayload={{ warehouse_map_id: warehouseMapId, phase: "on_demand" }}
        />
      ) : null}

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
          onClick={() => {
            void refreshTargets();
            void loadTablePage();
          }}
          disabled={targetsLoading || tableLoading}
        >
          Refresh
        </Button>
        <Button
          variant="outlined"
          size="small"
          color="error"
          startIcon={<DeleteRoundedIcon />}
          onClick={() => void handleDeleteSelected()}
          disabled={targetsLoading || deleting || selectedIds.length === 0}
        >
          {deleting ? "Deleting…" : "Delete selected"}
        </Button>
      </Stack>

      <Table size="small" aria-label="warehouse scan targets">
        <TableHead>
          <TableRow>
            <TableCell padding="checkbox">
              <Checkbox
                indeterminate={someSelected}
                checked={allSelected}
                disabled={tableRows.length === 0}
                onChange={(event) =>
                  setSelectedIds(
                    event.target.checked
                      ? tableRows.map((target) => target.id)
                      : [],
                  )
                }
                inputProps={{ "aria-label": "Select all targets" }}
              />
            </TableCell>
            <TableCell>Location</TableCell>
            <TableCell>Product</TableCell>
            <TableCell>Target Point</TableCell>
            <TableCell>Scan Pose</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {tableLoading ? (
            <TableRow>
              <TableCell colSpan={6}>
                <Typography variant="body2" color="text.secondary">
                  Loading scan targets…
                </Typography>
              </TableCell>
            </TableRow>
          ) : tableRows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6}>
                <Typography variant="body2" color="text.secondary">
                  No saved targets yet. Pick a location on the map and save.
                </Typography>
              </TableCell>
            </TableRow>
          ) : (
            tableRows.map((target: WarehouseScanTarget) => (
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
                  <IconButton
                    size="small"
                    color="error"
                    onClick={() => void handleDelete(target.id)}
                    aria-label="Archive scan target"
                  >
                    <DeleteRoundedIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
      <TablePagination
        component="div"
        count={tableTotal}
        page={tablePage}
        onPageChange={(_event, nextPage) => setTablePage(nextPage)}
        rowsPerPage={TABLE_PAGE_SIZE}
        rowsPerPageOptions={[TABLE_PAGE_SIZE]}
      />
    </Stack>
  );
}
