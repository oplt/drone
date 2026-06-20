import { useState } from "react";
import { Box, InputAdornment, MenuItem, Stack, TextField } from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { WarehouseSensorRig, WarehouseSensorRigHealth } from "../types";
import {
  COMPACT_FIELD_SX,
  SENSOR_RIG_CREATE_FIELDS,
  type SensorRigForm,
} from "../warehousePageSupport";

type Props = {
  rigs: WarehouseSensorRig[];
  selectedId: number | null;
  health: WarehouseSensorRigHealth | null;
  loading: boolean;
  saving: boolean;
  deleting: boolean;
  onSelect: (id: number | null) => void;
  onRefresh: () => void;
  onCalibrate: () => void;
  onCreate: (form: SensorRigForm) => Promise<boolean>;
  onDelete: (rig: WarehouseSensorRig | undefined) => void;
};

const emptyForm: SensorRigForm = {
  name: "",
  camera_model: "",
  stereo_baseline_m: "",
  intrinsics_url: "",
  extrinsics_url: "",
  firmware_version: "",
};

export function WarehouseSensorRigSetupPanel({
  rigs,
  selectedId,
  health,
  loading,
  saving,
  deleting,
  onSelect,
  onRefresh,
  onCalibrate,
  onCreate,
  onDelete,
}: Props) {
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<SensorRigForm>(emptyForm);
  const selectedRig = rigs.find((rig) => rig.id === selectedId);
  const helperText = health
    ? health.ready
      ? health.perception?.ready
        ? "Ready"
        : (health.warnings?.[0] ?? "Registered — perception starts with flight")
      : (health.blockers[0] ?? "Not ready")
    : undefined;

  return (
    <>
      <Stack direction="row" spacing={0.75} alignItems="flex-start">
        <TextField
          variant="filled"
          select
          size="small"
          label="Camera + IMU Rig"
          value={selectedId == null ? "" : String(selectedId)}
          onChange={(event) =>
            onSelect(event.target.value ? Number(event.target.value) : null)
          }
          helperText={helperText}
          sx={{ ...COMPACT_FIELD_SX, flex: 1 }}
        >
          {rigs.length === 0 && (
            <MenuItem value="">No sensor rigs registered</MenuItem>
          )}
          {rigs.map((rig) => (
            <MenuItem key={rig.id} value={String(rig.id)}>
              {rig.name} • {rig.camera_model} • {rig.calibration_status}
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
            variant="check"
            title="Calibrated"
            loading={saving}
            disabled={selectedId == null}
            onClick={onCalibrate}
          />
          <ActionIconButton
            variant="add"
            title={showCreate ? "Cancel" : "New Sensor Rig"}
            color={showCreate ? "primary" : "default"}
            onClick={() => setShowCreate((value) => !value)}
          />
          <ActionIconButton
            variant="delete"
            title={deleting ? "Deleting…" : "Delete Sensor Rig"}
            color="error"
            loading={deleting}
            disabled={selectedId == null}
            onClick={() => onDelete(selectedRig)}
          />
        </Stack>
      </Stack>
      {showCreate && (
        <Stack
          spacing={1}
          sx={{
            mt: 1,
            p: 1.5,
            borderRadius: 1,
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "repeat(3, minmax(72px, 1fr))",
              gap: 0.75,
            }}
          >
            {SENSOR_RIG_CREATE_FIELDS.map((field) => (
              <TextField
                variant="filled"
                key={field.key}
                size="small"
                fullWidth
                type={field.type}
                label={field.label}
                value={form[field.key]}
                sx={COMPACT_FIELD_SX}
                inputProps={
                  field.type === "number"
                    ? { min: 0.01, step: 0.01 }
                    : undefined
                }
                InputProps={
                  field.adornment
                    ? {
                        endAdornment: (
                          <InputAdornment position="end">
                            {field.adornment}
                          </InputAdornment>
                        ),
                      }
                    : undefined
                }
                onChange={(event) =>
                  setForm({ ...form, [field.key]: event.target.value })
                }
              />
            ))}
          </Box>
          <Stack direction="row" justifyContent="flex-end">
            <ActionIconButton
              variant="add"
              title={saving ? "Saving…" : "Create Sensor Rig"}
              color="primary"
              loading={saving}
              onClick={() => {
                void onCreate(form).then((created) => {
                  if (!created) return;
                  setForm(emptyForm);
                  setShowCreate(false);
                });
              }}
            />
          </Stack>
        </Stack>
      )}
    </>
  );
}
