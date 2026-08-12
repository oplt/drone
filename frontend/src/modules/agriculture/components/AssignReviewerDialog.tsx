import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useCurrentUser } from "../../session/hooks/useCurrentUser";

export function AssignReviewerDialog({
  open,
  pending = false,
  onClose,
  onAssign,
}: {
  open: boolean;
  pending?: boolean;
  onClose: () => void;
  onAssign: (userId: number, dueAt: string | null) => void;
}) {
  const { user, isLoading } = useCurrentUser();
  const [dueAt, setDueAt] = useState("");
  return (
    <Dialog open={open} onClose={pending ? undefined : onClose} fullWidth maxWidth="xs" aria-labelledby="assign-reviewer-title">
      <DialogTitle id="assign-reviewer-title">Assign reviewer</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ pt: 1 }}>
          {user ? (
            <Alert severity="info">
              Assigning to signed-in reviewer <strong>{user.first_name || user.email}</strong>.
            </Alert>
          ) : (
            <Typography role="status">{isLoading ? "Loading reviewer identity…" : "Reviewer identity is unavailable."}</Typography>
          )}
          <TextField type="datetime-local" label="Review due (optional)" value={dueAt} onChange={(event) => setDueAt(event.target.value)} InputLabelProps={{ shrink: true }} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={pending}>Cancel</Button>
        <Button variant="contained" disabled={!user || pending} onClick={() => user && onAssign(user.id, dueAt ? new Date(dueAt).toISOString() : null)}>
          {pending ? "Assigning…" : "Assign to me"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
