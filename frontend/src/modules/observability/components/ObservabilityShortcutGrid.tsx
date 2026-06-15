import type { ReactNode } from "react";
import Box from "@mui/material/Box";

export const SHORTCUTS_PER_ROW = 4;

type ObservabilityShortcutGridProps = {
  children: ReactNode;
};

export default function ObservabilityShortcutGrid({ children }: ObservabilityShortcutGridProps) {
  return (
    <Box
      sx={{
        overflowX: "auto",
        borderRadius: 2,
        WebkitOverflowScrolling: "touch",
      }}
    >
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: `repeat(${SHORTCUTS_PER_ROW}, minmax(0, 1fr))`,
          minWidth: { xs: 720, sm: "100%" },
          borderTop: "1px solid",
          borderLeft: "1px solid",
          borderColor: "divider",
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
