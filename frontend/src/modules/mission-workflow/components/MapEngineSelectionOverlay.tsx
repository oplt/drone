import type { ReactNode } from "react";
import { Paper } from "@mui/material";

export function MapEngineSelectionOverlay({ children }: { children: ReactNode }) {
  return (
    <Paper
      elevation={0}
      sx={{
        position: "absolute",
        left: 10,
        bottom: 10,
        zIndex: 1300,
        pointerEvents: "auto",
        p: 1,
        borderRadius: 1.5,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "rgba(255, 255, 255, 0.5)",
        backdropFilter: "blur(0.5px)",
        maxWidth: "calc(100% - 20px)",
      }}
    >
      {children}
    </Paper>
  );
}
