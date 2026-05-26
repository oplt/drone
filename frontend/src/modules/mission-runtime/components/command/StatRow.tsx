import { Stack, Typography } from "@mui/material";

export function StatRow({
  label,
  value,
  valueSx,
}: {
  label: string;
  value: string;
  valueSx?: Record<string, unknown>;
}) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 600, ...valueSx }}>
        {value}
      </Typography>
    </Stack>
  );
}
