import { Alert, Box, Button } from "@mui/material";

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
      <Button size="small" onClick={onClearAll} sx={{ mt: 1 }}>
        Clear All Errors
      </Button>
    </Box>
  );
}
