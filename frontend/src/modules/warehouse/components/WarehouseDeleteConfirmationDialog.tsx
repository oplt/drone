import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from "@mui/material";

export type WarehouseDeleteTarget = {
  kind: "map" | "sensor rig" | "dock" | "scan result";
  label: string;
  assetCount?: number;
  onConfirm: () => void;
} | null;

export function WarehouseDeleteConfirmationDialog({
  target,
  busy = false,
  onClose,
}: {
  target: WarehouseDeleteTarget;
  busy?: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={Boolean(target)}
      onClose={busy ? undefined : onClose}
      maxWidth="xs"
      fullWidth
    >
      <DialogTitle>Delete {target?.kind}</DialogTitle>
      <DialogContent>
        <Stack spacing={1}>
          <Typography variant="body2">
            {target ? `Delete ${target.kind} "${target.label}"?` : ""}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {target?.assetCount != null
              ? `${target.assetCount} linked asset${target.assetCount === 1 ? "" : "s"} will be removed or detached.`
              : "This action cannot be undone."}
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button
          color="error"
          variant="contained"
          disabled={!target || busy}
          onClick={() => target?.onConfirm()}
        >
          Delete
        </Button>
      </DialogActions>
    </Dialog>
  );
}
