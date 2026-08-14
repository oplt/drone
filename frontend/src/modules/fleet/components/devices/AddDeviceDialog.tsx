import { useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { ActionIconButton } from "../../../../shared/ui/ActionIconButton";
import { createDevice } from "../../api/fleetApi";
import { FLEET_DEVICE_STATUSES } from "../../fleetPageConstants";

type AddDeviceDialogProps = {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
};

export function AddDeviceDialog({ open, onClose, onCreated }: AddDeviceDialogProps) {
  const [deviceId, setDeviceId] = useState("");
  const [deviceName, setDeviceName] = useState("");
  const [status, setStatus] = useState<string>(FLEET_DEVICE_STATUSES[0]);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleClose = () => {
    setDeviceId("");
    setDeviceName("");
    setStatus(FLEET_DEVICE_STATUSES[0]);
    setNotes("");
    setError("");
    onClose();
  };

  const handleSubmit = async () => {
    if (!deviceId.trim() || !deviceName.trim()) return;
    setSaving(true);
    setError("");
    try {
      await createDevice({
        device_id: deviceId.trim(),
        device_name: deviceName.trim(),
        status,
        notes: notes.trim() || null,
      });
      onCreated();
      handleClose();
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Failed to add device");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Device</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            label="Device ID"
            value={deviceId}
            onChange={(event) => setDeviceId(event.target.value)}
            fullWidth
            autoFocus
          />
          <TextField
            label="Device name"
            value={deviceName}
            onChange={(event) => setDeviceName(event.target.value)}
            fullWidth
          />
          <Select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            fullWidth
            displayEmpty
          >
            {FLEET_DEVICE_STATUSES.map((deviceStatus) => (
              <MenuItem key={deviceStatus} value={deviceStatus}>
                {deviceStatus.charAt(0).toUpperCase() + deviceStatus.slice(1)}
              </MenuItem>
            ))}
          </Select>
          <TextField
            label="Notes (optional)"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            fullWidth
            multiline
            minRows={2}
          />
          {error && (
            <Typography color="error" variant="body2">
              {error}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <ActionIconButton variant="close" title="Cancel" onClick={handleClose} />
        <ActionIconButton
          variant="add"
          title={saving ? "Adding…" : "Add"}
          color="primary"
          loading={saving}
          disabled={saving || !deviceId.trim() || !deviceName.trim()}
          onClick={() => void handleSubmit()}
        />
      </DialogActions>
    </Dialog>
  );
}
