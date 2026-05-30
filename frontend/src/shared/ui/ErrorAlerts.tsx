import { Alert, Box } from "@mui/material";
import { ActionIconButton } from "./ActionIconButton";

export function ErrorAlerts({
  errors,
  onDismiss,
  onClearAll,
  sx,
}: {
  errors: string[];
  onDismiss: (index: number) => void;
  onClearAll: () => void;
  sx?: any;
}) {
  if (!errors.length) return null;

  return (
    <Box sx={{ mb: 2, ...sx }}>
      {errors.map((error, idx) => (
        <Alert
          key={`${idx}-${error}`}
          severity="error"
          sx={{ mb: 1 }}
          onClose={() => onDismiss(idx)}
        >
          {error}
        </Alert>
      ))}
      <ActionIconButton variant="close" title="Clear All Errors" onClick={onClearAll} sx={{ mt: 1 }} />
    </Box>
  );
}
