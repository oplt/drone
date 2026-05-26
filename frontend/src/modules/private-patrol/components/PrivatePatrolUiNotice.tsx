import { Alert, Snackbar } from "@mui/material";
import type { UiNotice } from "../types";

export function PrivatePatrolUiNotice({
  notice,
  onClose,
}: {
  notice: UiNotice;
  onClose: (_event?: unknown, reason?: string) => void;
}) {
  return (
    <Snackbar
      open={notice.open}
      autoHideDuration={4000}
      onClose={onClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
    >
      <Alert onClose={onClose} severity={notice.severity} sx={{ width: "100%" }}>
        {notice.message}
      </Alert>
    </Snackbar>
  );
}
