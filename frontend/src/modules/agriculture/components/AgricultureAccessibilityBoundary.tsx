import { Box, GlobalStyles } from "@mui/material";
import type { ReactNode } from "react";
import { agricultureAccessibilityStyles } from "./accessibilityStyles";

export function AgricultureAccessibilityBoundary({
  children,
  component = "main",
}: {
  children: ReactNode;
  component?: "main" | "section" | "div";
}) {
  return (
    <>
      <GlobalStyles styles={agricultureAccessibilityStyles} />
      <Box component={component} className="agriculture-surface">
        {children}
      </Box>
    </>
  );
}
