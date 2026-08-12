import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from "@mui/material";
import { useState } from "react";

const reasonTemplates = ["Operational follow-up", "Data quality correction", "Retention policy", "Safety requirement"];

export function ReasonConfirmDialog({
  open,
  title,
  confirmLabel,
  description,
  pending = false,
  irreversible = false,
  onClose,
  onConfirm,
}: {
  open: boolean;
  title: string;
  confirmLabel: string;
  description?: string;
  pending?: boolean;
  irreversible?: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}) {
  if (!open) return null;
  return (
    <ReasonConfirmDialogContent
      title={title}
      confirmLabel={confirmLabel}
      description={description}
      pending={pending}
      irreversible={irreversible}
      onClose={onClose}
      onConfirm={onConfirm}
    />
  );
}

function ReasonConfirmDialogContent({
  title,
  confirmLabel,
  description,
  pending,
  irreversible,
  onClose,
  onConfirm,
}: Omit<Parameters<typeof ReasonConfirmDialog>[0], "open">) {
  const [template, setTemplate] = useState("");
  const [details, setDetails] = useState("");
  const reason = [template, details.trim()].filter(Boolean).join(": ");
  return (
    <Dialog open onClose={pending ? undefined : onClose} fullWidth maxWidth="xs" aria-labelledby="reason-confirm-title">
      <DialogTitle id="reason-confirm-title">{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ pt: 1 }}>
          {description ? <Alert severity={irreversible ? "warning" : "info"}>{description}</Alert> : null}
          <TextField select label="Reason" value={template} onChange={(event) => setTemplate(event.target.value)} required>
            {reasonTemplates.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
          </TextField>
          <TextField label="Additional details" value={details} onChange={(event) => setDetails(event.target.value)} multiline minRows={2} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={pending}>Cancel</Button>
        <Button variant="contained" color={irreversible ? "warning" : "primary"} disabled={!reason || pending} onClick={() => onConfirm(reason)}>
          {pending ? "Working…" : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
