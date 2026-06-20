import { useState } from "react";
import { InputAdornment, MenuItem, Stack, TextField } from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { WarehouseMapOut } from "../types";
import type { WarehouseScannedMapResponse } from "../types/missions";
import { getWarehouseMapId } from "../scannedMapSelectors";
import { COMPACT_FIELD_SX, type CreateMapForm } from "../warehousePageSupport";

type Props = {
  maps: WarehouseMapOut[];
  scannedMaps: WarehouseScannedMapResponse[];
  selectedId: number | null;
  loading: boolean;
  creating: boolean;
  deleting: boolean;
  onSelect: (id: number | null) => void;
  onRefresh: () => void;
  onCreate: (form: CreateMapForm) => Promise<boolean>;
  onDelete: (map: WarehouseMapOut | undefined, assetCount: number) => void;
};

const emptyForm: CreateMapForm = { name: "", width_m: "", length_m: "" };

export function WarehouseMapSetupPanel({
  maps,
  scannedMaps,
  selectedId,
  loading,
  creating,
  deleting,
  onSelect,
  onRefresh,
  onCreate,
  onDelete,
}: Props) {
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateMapForm>(emptyForm);
  const selectedMap = maps.find((map) => map.id === selectedId);

  return (
    <Stack
      direction="row"
      spacing={0.75}
      alignItems="flex-start"
      useFlexGap
      sx={{ flexWrap: "wrap", minWidth: 0 }}
    >
      <TextField
        variant="filled"
        select
        size="small"
        label="Map"
        value={selectedId == null ? "" : String(selectedId)}
        onChange={(event) =>
          onSelect(event.target.value ? Number(event.target.value) : null)
        }
        disabled={loading}
        helperText={
          maps.length === 0
            ? "No maps yet"
            : selectedMap?.area_m2 != null
              ? `${Math.round(selectedMap.area_m2)} m²`
              : selectedId != null
                ? `#${selectedId}`
                : undefined
        }
        sx={{
          ...COMPACT_FIELD_SX,
          flex: "1 1 160px",
          minWidth: 140,
          maxWidth: 360,
        }}
      >
        {maps.length === 0 && (
          <MenuItem value="">No warehouse maps registered</MenuItem>
        )}
        {maps.map((map) => (
          <MenuItem key={map.id} value={String(map.id)}>
            {map.name}
            {map.area_m2 != null ? ` • ${Math.round(map.area_m2)} m²` : ""}
          </MenuItem>
        ))}
      </TextField>
      <Stack direction="row" spacing={0.25} sx={{ pt: 0.25 }}>
        <ActionIconButton
          variant="refresh"
          title="Refresh"
          loading={loading}
          onClick={onRefresh}
        />
        <ActionIconButton
          variant="add"
          title={showCreate ? "Cancel" : "New Map"}
          color={showCreate ? "primary" : "default"}
          onClick={() => setShowCreate((value) => !value)}
        />
        <ActionIconButton
          variant="delete"
          title={deleting ? "Deleting…" : "Delete Map"}
          color="error"
          loading={deleting}
          disabled={selectedId == null}
          onClick={() =>
            onDelete(
              selectedMap,
              scannedMaps.filter(
                (scan) => getWarehouseMapId(scan) === selectedId,
              ).length,
            )
          }
        />
      </Stack>
      {showCreate && (
        <>
          <TextField
            variant="filled"
            size="small"
            label="Name"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            placeholder="e.g. Aisle A–F"
            sx={{ ...COMPACT_FIELD_SX, flex: "1 1 120px", minWidth: 100 }}
          />
          {(["width_m", "length_m"] as const).map((key) => (
            <TextField
              key={key}
              variant="filled"
              size="small"
              type="number"
              label={key === "width_m" ? "Width" : "Length"}
              inputProps={{ min: 0.1, step: 0.5 }}
              InputProps={{
                endAdornment: <InputAdornment position="end">m</InputAdornment>,
              }}
              value={form[key]}
              onChange={(event) =>
                setForm({ ...form, [key]: event.target.value })
              }
              sx={{ ...COMPACT_FIELD_SX, flex: "0 1 88px", minWidth: 72 }}
            />
          ))}
          <ActionIconButton
            variant="add"
            title={creating ? "Creating…" : "Create Map"}
            color="primary"
            loading={creating}
            onClick={() => {
              void onCreate(form).then((created) => {
                if (!created) return;
                setForm(emptyForm);
                setShowCreate(false);
              });
            }}
            sx={{ mt: 0.25 }}
          />
        </>
      )}
    </Stack>
  );
}
