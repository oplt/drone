import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from "@mui/material";
import type { FieldFeature } from "../../fields";

export function FieldDeleteDialog({
  field,
  deleting,
  onClose,
  onConfirm,
}: {
  field: FieldFeature | null;
  deleting: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={Boolean(field)} onClose={onClose}>
      <DialogTitle>Delete Field</DialogTitle>
      <DialogContent>
        <DialogContentText>
          Delete field "{field?.name}"? This action cannot be undone.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={deleting}>
          Cancel
        </Button>
        <Button
          color="error"
          variant="contained"
          onClick={onConfirm}
          disabled={deleting}
        >
          {deleting ? "Deleting..." : "Delete"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
