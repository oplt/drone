import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Chip,
  CircularProgress,
  InputAdornment,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import {
  createWarehouseDock,
  deleteWarehouseDock,
  listWarehouseDocks,
  updateWarehouseDock,
} from "../api/warehouseMapsApi";
import type { WarehouseDockPayload, WarehouseDockStation } from "../types";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import {
  WarehouseDeleteConfirmationDialog,
  type WarehouseDeleteTarget,
} from "./WarehouseDeleteConfirmationDialog";

const DOCK_FIELD_SX = {
  "& .MuiFilledInput-root": {
    backgroundColor: "action.hover",
    "&:hover": { backgroundColor: "action.selected" },
    "&.Mui-focused": { backgroundColor: "action.selected" },
  },
} as const;

type Props = {
  warehouseMapId: number | null;
  selectedDockId: number | null;
  onSelectedDockIdChange: (dockId: number | null) => void;
  getToken: () => string | null;
  onError: (message: string) => void;
  embedded?: boolean;
};

const ZERO_POSE = { x_m: 0, y_m: 0, z_m: 0, yaw_deg: 0 };

function markerStatus(dock: WarehouseDockStation | undefined): {
  label: string;
  color: "success" | "warning" | "default";
} {
  if (!dock) return { label: "No dock", color: "default" };
  if (dock.marker_visible === true)
    return { label: "Marker visible", color: "success" };
  if (dock.marker_id) return { label: "Marker pending", color: "warning" };
  return { label: "No marker", color: "default" };
}

export function WarehouseDockPanel({
  warehouseMapId,
  selectedDockId,
  onSelectedDockIdChange,
  getToken,
  onError,
  embedded = false,
}: Props) {
  const [docks, setDocks] = useState<WarehouseDockStation[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [markerId, setMarkerId] = useState("");
  const [markerFamily, setMarkerFamily] = useState("apriltag_36h11");
  const [markerSizeM, setMarkerSizeM] = useState("0.16");
  const [deleteTarget, setDeleteTarget] = useState<WarehouseDeleteTarget>(null);

  const selectedDock = useMemo(
    () => docks.find((dock) => dock.id === selectedDockId),
    [docks, selectedDockId],
  );
  const status = markerStatus(selectedDock);

  const loadDocks = useCallback(async () => {
    const token = getToken();
    if (!token || warehouseMapId == null) {
      setDocks([]);
      onSelectedDockIdChange(null);
      return;
    }
    setLoading(true);
    try {
      const next = await listWarehouseDocks(warehouseMapId, token);
      setDocks(next);
      if (
        selectedDockId != null &&
        !next.some((dock) => dock.id === selectedDockId)
      ) {
        onSelectedDockIdChange(null);
      }
    } catch (error) {
      onError(
        `Dock stations could not be loaded: ${error instanceof Error ? error.message : error}`,
      );
    } finally {
      setLoading(false);
    }
  }, [
    getToken,
    onError,
    onSelectedDockIdChange,
    selectedDockId,
    warehouseMapId,
  ]);

  useEffect(() => {
    void loadDocks();
  }, [loadDocks]);

  const buildPayload = (): WarehouseDockPayload => ({
    name: name.trim() || "Dock Station",
    marker_id: markerId.trim() || null,
    marker_family: markerFamily.trim() || "apriltag_36h11",
    marker_size_m: markerSizeM ? Number(markerSizeM) : null,
    precision_required: true,
    pose: ZERO_POSE,
    entry_pose: ZERO_POSE,
    exit_pose: ZERO_POSE,
  });

  const saveDock = async () => {
    const token = getToken();
    if (!token || warehouseMapId == null) return;
    setSaving(true);
    try {
      const payload = buildPayload();
      const dock =
        selectedDockId == null
          ? await createWarehouseDock(warehouseMapId, payload, token)
          : await updateWarehouseDock(
              warehouseMapId,
              selectedDockId,
              payload,
              token,
            );
      onSelectedDockIdChange(dock.id);
      setName("");
      setMarkerId("");
      await loadDocks();
    } catch (error) {
      onError(
        `Dock station could not be saved: ${error instanceof Error ? error.message : error}`,
      );
    } finally {
      setSaving(false);
    }
  };

  const removeDock = async (dockId: number) => {
    const token = getToken();
    if (!token || warehouseMapId == null) return;
    setSaving(true);
    try {
      await deleteWarehouseDock(warehouseMapId, dockId, token);
      if (selectedDockId === dockId) onSelectedDockIdChange(null);
      await loadDocks();
    } catch (error) {
      onError(
        `Dock station could not be deleted: ${error instanceof Error ? error.message : error}`,
      );
    } finally {
      setSaving(false);
      setDeleteTarget(null);
    }
  };

  const content = (
    <>
      <Stack spacing={1.25}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent={embedded ? "flex-end" : "space-between"}
        >
          {!embedded && (
            <Typography variant="subtitle1">Dock Station</Typography>
          )}
          <Stack direction="row" spacing={0.25} alignItems="center">
            <Chip size="small" label={status.label} color={status.color} />
            {loading && <CircularProgress size={16} />}
            <ActionIconButton
              variant="refresh"
              title="Refresh"
              disabled={!warehouseMapId}
              loading={loading}
              onClick={() => {
                void loadDocks();
              }}
            />
          </Stack>
        </Stack>

        <TextField
          variant="filled"
          select
          fullWidth
          size="small"
          sx={DOCK_FIELD_SX}
          label={
            <InfoLabel
              label="Start dock"
              info="Optional local-frame anchor for takeoff and return."
            />
          }
          disabled={!warehouseMapId || loading}
          value={selectedDockId != null ? String(selectedDockId) : ""}
          onChange={(event) =>
            onSelectedDockIdChange(
              event.target.value ? Number(event.target.value) : null,
            )
          }
          helperText={
            selectedDock?.last_observed_at
              ? `Last marker ${selectedDock.last_observed_at}`
              : undefined
          }
        >
          <MenuItem value="">No dock anchor</MenuItem>
          {docks.map((dock) => (
            <MenuItem key={dock.id} value={String(dock.id)}>
              {dock.name} {dock.marker_id ? `- ${dock.marker_id}` : ""}
            </MenuItem>
          ))}
        </TextField>

        {warehouseMapId == null ? (
          <Alert severity="info">
            Select a warehouse map before configuring a dock.
          </Alert>
        ) : (
          <Stack spacing={1}>
            <TextField
              variant="filled"
              size="small"
              sx={DOCK_FIELD_SX}
              label={
                selectedDockId == null ? "New dock name" : "Edit dock name"
              }
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                variant="filled"
                size="small"
                sx={DOCK_FIELD_SX}
                label="Marker ID"
                value={markerId}
                onChange={(event) => setMarkerId(event.target.value)}
              />
              <TextField
                variant="filled"
                size="small"
                sx={DOCK_FIELD_SX}
                label="Family"
                value={markerFamily}
                onChange={(event) => setMarkerFamily(event.target.value)}
              />
              <TextField
                variant="filled"
                size="small"
                sx={DOCK_FIELD_SX}
                label="Size"
                type="number"
                value={markerSizeM}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">m</InputAdornment>
                  ),
                }}
                onChange={(event) => setMarkerSizeM(event.target.value)}
              />
            </Stack>
            <Stack direction="row" spacing={0.25} alignItems="center">
              <ActionIconButton
                variant={selectedDockId == null ? "add" : "upgrade"}
                title={selectedDockId == null ? "Create Dock" : "Update Dock"}
                color="primary"
                loading={saving}
                onClick={() => {
                  void saveDock();
                }}
              />
              {selectedDockId != null && (
                <ActionIconButton
                  variant="delete"
                  title="Delete Dock"
                  color="error"
                  loading={saving}
                  onClick={() => {
                    setDeleteTarget({
                      kind: "dock",
                      label: selectedDock?.name ?? `Dock #${selectedDockId}`,
                      assetCount: 1,
                      onConfirm: () => {
                        void removeDock(selectedDockId);
                      },
                    });
                  }}
                />
              )}
            </Stack>
          </Stack>
        )}
      </Stack>
      <WarehouseDeleteConfirmationDialog
        target={deleteTarget}
        busy={saving}
        onClose={() => setDeleteTarget(null)}
      />
    </>
  );

  if (embedded) return content;

  return (
    <Paper
      variant="outlined"
      sx={{ p: 2, borderRadius: 2, borderColor: "divider" }}
    >
      {content}
    </Paper>
  );
}
