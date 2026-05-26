import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import type { ReactNode } from "react";
import NavbarBreadcrumbs from "./NavbarBreadcrumbs";

export type ConsoleToolbarProps = {
  /** Optional search or filter control shown before trailing actions. */
  leading?: ReactNode;
  /** Status chips, notifications trigger, theme toggle, etc. */
  trailing?: ReactNode;
};

/** Domain-free top bar for console views (breadcrumbs + utility slots). */
export default function ConsoleToolbar({ leading, trailing }: ConsoleToolbarProps) {
  return (
    <Paper
      variant="outlined"
      component="header"
      sx={{
        display: { xs: "none", md: "block" },
        width: "100%",
        maxWidth: { sm: "100%", md: "1700px" },
        p: 1.5,
        borderRadius: 999,
        backgroundColor: "rgba(255,255,255,0.76)",
        backdropFilter: "blur(16px)",
        '[data-mui-color-scheme="dark"] &': {
          backgroundColor: "rgba(14,18,22,0.76)",
          borderColor: "rgba(122, 160, 145, 0.18)",
        },
      }}
    >
      <Stack
        direction="row"
        sx={{
          width: "100%",
          alignItems: "center",
          justifyContent: "space-between",
        }}
        spacing={2}
      >
        <NavbarBreadcrumbs />
        <Stack direction="row" sx={{ gap: 1, alignItems: "center" }} role="toolbar" aria-label="Console actions">
          {leading}
          {trailing}
        </Stack>
      </Stack>
    </Paper>
  );
}
