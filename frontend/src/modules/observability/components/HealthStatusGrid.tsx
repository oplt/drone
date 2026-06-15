import type { ReactNode } from "react";
import Box from "@mui/material/Box";

const HEALTH_CELL_COUNT = 9;

type HealthStatusGridProps = {
  children: ReactNode;
};

export default function HealthStatusGrid({ children }: HealthStatusGridProps) {
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
          gridTemplateColumns: `repeat(${HEALTH_CELL_COUNT}, minmax(0, 1fr))`,
          minWidth: { xs: 900, sm: "100%" },
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
