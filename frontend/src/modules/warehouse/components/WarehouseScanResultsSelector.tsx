import { CircularProgress, MenuItem, Stack, TextField } from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import {
  getWarehouseMapId,
  getWarehouseName,
} from "../scannedMapSelectors";
import type { WarehouseScannedMapResponse } from "../types/missions";

type Props = {
  maps: WarehouseScannedMapResponse[];
  selectedMap: WarehouseScannedMapResponse | null;
  loading: boolean;
  deleting?: boolean;
  onSelect: (jobId: number | null) => void;
  onRefresh: () => void;
  onDelete?: () => void;
};

function formatTimestamp(value?: string | null): string {
  if (!value) return "unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function WarehouseScanResultsSelector({
  maps,
  selectedMap,
  loading,
  deleting = false,
  onSelect,
  onRefresh,
  onDelete,
}: Props) {
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems="flex-start">
      <TextField
        variant="filled"
        select
        disabled={!loading && maps.length === 0}
        size="small"
        label="Previous Scan Results"
        value={selectedMap ? String(selectedMap.job_id) : ""}
        onChange={(event) => {
          const raw = event.target.value;
          onSelect(raw ? Number(raw) : null);
        }}
        helperText={
          selectedMap
            ? selectedMap.status === "failed" && selectedMap.error
              ? selectedMap.error
              : `${getWarehouseName(selectedMap)} (#${getWarehouseMapId(selectedMap)})`
            : "Select a scan result to show it in the 3D map."
        }
        sx={{ flex: 1, minWidth: { xs: "100%", sm: 220 } }}
      >
        {maps.length === 0 && (
          <MenuItem value="" disabled>
            No scanned maps available
          </MenuItem>
        )}
        {maps.map((map) => (
          <MenuItem key={map.job_id} value={String(map.job_id)}>
            {`${getWarehouseName(map)} · ${
              map.source === "simulation" ? "simulation" : "real flight"
            } · v${map.model_version} · ${map.status} · ${formatTimestamp(map.created_at)}`}
          </MenuItem>
        ))}
      </TextField>
      <Stack direction="row" spacing={0.25} alignItems="center" sx={{ pt: { sm: 1.5 } }}>
        {loading ? (
          <CircularProgress size={20} />
        ) : (
          <ActionIconButton variant="refresh" title="Refresh scan results" onClick={onRefresh} />
        )}
        {onDelete && (
          <ActionIconButton
            variant="delete"
            title={deleting ? "Deleting scan result" : "Delete scan result"}
            color="error"
            loading={deleting}
            disabled={!selectedMap}
            onClick={onDelete}
          />
        )}
      </Stack>
    </Stack>
  );
}
