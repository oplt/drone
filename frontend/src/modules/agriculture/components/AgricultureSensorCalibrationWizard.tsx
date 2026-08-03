import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useRegisterAgricultureSensorCalibration } from "../hooks";

const SENSOR_TYPES = ["multispectral", "thermal", "weather", "humidity", "soil_moisture", "irrigation"] as const;

export function AgricultureSensorCalibrationWizard() {
  const register = useRegisterAgricultureSensorCalibration();
  const [form, setForm] = useState({ id: "", sensor_serial: "", sensor_type: "multispectral" as (typeof SENSOR_TYPES)[number], version: "", calibration_kind: "radiometric", checksum: "", valid_from: "", valid_until: "" });
  const set = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const valid = Object.values(form).every(Boolean) && form.checksum.length >= 16;
  return (
    <Paper component="section" aria-labelledby="sensor-calibration-wizard-heading" variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Typography id="sensor-calibration-wizard-heading" variant="subtitle2">Register sensor calibration</Typography>
        <Typography variant="caption" color="text.secondary">Register the immutable calibration artifact before multispectral, thermal, or external-sensor outputs can be measured.</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField size="small" label="Calibration ID" value={form.id} onChange={(event) => set("id", event.target.value)} required />
          <TextField size="small" label="Sensor serial" value={form.sensor_serial} onChange={(event) => set("sensor_serial", event.target.value)} required />
          <TextField select size="small" label="Sensor type" value={form.sensor_type} onChange={(event) => set("sensor_type", event.target.value)}>
            {SENSOR_TYPES.map((type) => <MenuItem key={type} value={type}>{type.replaceAll("_", " ")}</MenuItem>)}
          </TextField>
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField size="small" label="Calibration version" value={form.version} onChange={(event) => set("version", event.target.value)} required />
          <TextField size="small" label="Calibration kind" value={form.calibration_kind} onChange={(event) => set("calibration_kind", event.target.value)} required />
          <TextField size="small" label="Artifact checksum" helperText="At least 16 characters" value={form.checksum} onChange={(event) => set("checksum", event.target.value)} required />
          <TextField size="small" type="datetime-local" label="Valid from" value={form.valid_from} onChange={(event) => set("valid_from", event.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" type="datetime-local" label="Valid until" value={form.valid_until} onChange={(event) => set("valid_until", event.target.value)} InputLabelProps={{ shrink: true }} />
        </Stack>
        <Button variant="outlined" size="small" sx={{ alignSelf: "flex-start" }} disabled={!valid || register.isPending} onClick={() => register.mutate({ ...form, valid_from: form.valid_from ? new Date(form.valid_from).toISOString() : null, valid_until: form.valid_until ? new Date(form.valid_until).toISOString() : null, calibration_data: { registered_from: "agriculture-ui" } })}>
          {register.isPending ? "Registering…" : "Register calibration"}
        </Button>
        {register.isSuccess ? <Alert severity="success">Calibration registered. Re-run sensor readiness before processing.</Alert> : null}
        {register.isError ? <Alert severity="error">Calibration could not be registered. Check the ID, checksum, and tenant permissions.</Alert> : null}
      </Stack>
    </Paper>
  );
}
