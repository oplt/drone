import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Stack,
} from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { FieldFeature } from "../types";

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
        <Stack direction="row" spacing={0.25}>
          <ActionIconButton variant="close" title="Cancel" disabled={deleting} onClick={onClose} />
          <ActionIconButton
            variant="delete"
            title={deleting ? "Deleting…" : "Delete"}
            color="error"
            loading={deleting}
            onClick={onConfirm}
          />
        </Stack>
      </DialogActions>
    </Dialog>
  );
}
