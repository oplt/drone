import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

export type BulkActionBarProps = {
  selectedCount: number;
  /** Minimum selection before the bar appears (default 2). */
  minSelected?: number;
  label?: string;
  children: ReactNode;
};

/** Shared multi-select action strip — hidden until selection meets threshold. */
export function BulkActionBar({
  selectedCount,
  minSelected = 2,
  label,
  children,
}: BulkActionBarProps) {
  if (selectedCount < minSelected) return null;

  return (
    <Paper
      variant="outlined"
      role="toolbar"
      aria-label={label ?? "Bulk actions"}
      sx={{ p: 1.25, bgcolor: "action.hover" }}
    >
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        alignItems={{ sm: "center" }}
        flexWrap="wrap"
        useFlexGap
      >
        <Typography variant="body2" sx={{ fontWeight: 600, mr: { sm: 1 } }}>
          {selectedCount} selected
        </Typography>
        {children}
      </Stack>
    </Paper>
  );
}
