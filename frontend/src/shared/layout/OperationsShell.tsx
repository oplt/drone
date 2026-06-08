import CssBaseline from "@mui/material/CssBaseline";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import type { ThemeOptions } from "@mui/material/styles";
import type { ReactNode } from "react";
import AppTheme from "../theme/AppTheme";
import AppNavbar from "./AppNavbar";
import SideMenu from "./SideMenu";
import type { ShellUser } from "./types";

export type OperationsShellProps = {
  user: ShellUser;
  onLogout: () => void | Promise<void>;
  children: ReactNode;
  disableCustomTheme?: boolean;
  themeComponents?: ThemeOptions["components"];
};

export default function OperationsShell({
  user,
  onLogout,
  children,
  disableCustomTheme,
  themeComponents,
}: OperationsShellProps) {
  return (
    <AppTheme disableCustomTheme={disableCustomTheme} themeComponents={themeComponents}>
      <CssBaseline enableColorScheme />
      <Box sx={{ display: "flex", minHeight: "100dvh" }}>
        <SideMenu user={user} onLogout={onLogout} />
        <AppNavbar user={user} onLogout={onLogout} />
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            backgroundColor: "background.default",
            overflow: "auto",
            position: "relative",
          }}
        >
          <Stack
            spacing={2}
            sx={{
              alignItems: "stretch",
              width: "100%",
              px: { xs: 2, md: 3 },
              pb: 5,
              pt: { xs: 9, md: 2.5 },
              position: "relative",
              zIndex: 1,
            }}
          >
            {children}
          </Stack>
        </Box>
      </Box>
    </AppTheme>
  );
}
