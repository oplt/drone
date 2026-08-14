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
import { createCertification } from "../../api/fleetApi";
import { FLEET_CERT_TYPES } from "../../fleetPageConstants";

type AddCertDialogProps = {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
};

export function AddCertDialog({ open, onClose, onCreated }: AddCertDialogProps) {
  const [certType, setCertType] = useState<string>(FLEET_CERT_TYPES[0]);
  const [certNumber, setCertNumber] = useState("");
  const [issuedAt, setIssuedAt] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleClose = () => {
    setCertType(FLEET_CERT_TYPES[0]);
    setCertNumber("");
    setIssuedAt("");
    setExpiresAt("");
    setError("");
    onClose();
  };

  const handleSubmit = async () => {
    if (!certNumber.trim() || !issuedAt) return;
    setSaving(true);
    setError("");
    try {
      await createCertification({
        cert_type: certType,
        cert_number: certNumber.trim(),
        issued_at: issuedAt,
        expires_at: expiresAt || null,
      });
      onCreated();
      handleClose();
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Failed to add certification");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Certification</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Select
            value={certType}
            onChange={(event) => setCertType(event.target.value)}
            fullWidth
            displayEmpty
          >
            {FLEET_CERT_TYPES.map((type) => (
              <MenuItem key={type} value={type}>
                {type.replace(/_/g, " ")}
              </MenuItem>
            ))}
          </Select>
          <TextField
            label="Certificate number"
            value={certNumber}
            onChange={(event) => setCertNumber(event.target.value)}
            fullWidth
            autoFocus
          />
          <TextField
            label="Issued at"
            type="date"
            value={issuedAt}
            onChange={(event) => setIssuedAt(event.target.value)}
            fullWidth
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            label="Expires at (optional)"
            type="date"
            value={expiresAt}
            onChange={(event) => setExpiresAt(event.target.value)}
            fullWidth
            slotProps={{ inputLabel: { shrink: true } }}
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
          disabled={saving || !certNumber.trim() || !issuedAt}
          onClick={() => void handleSubmit()}
        />
      </DialogActions>
    </Dialog>
  );
}
