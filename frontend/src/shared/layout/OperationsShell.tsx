import CssBaseline from "@mui/material/CssBaseline";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import type { ThemeOptions } from "@mui/material/styles";
import { useEffect, useRef, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
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
  const location = useLocation();
  const mainRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    mainRef.current?.focus({ preventScroll: true });
  }, [location.pathname]);

  return (
    <AppTheme disableCustomTheme={disableCustomTheme} themeComponents={themeComponents}>
      <CssBaseline enableColorScheme />
      <Link
        href="#main-content"
        sx={{
          position: "absolute",
          left: 16,
          top: 8,
          zIndex: (theme) => theme.zIndex.tooltip + 1,
          px: 1.5,
          py: 0.75,
          borderRadius: 1,
          bgcolor: "background.paper",
          color: "text.primary",
          boxShadow: 3,
          transform: "translateY(-200%)",
          transition: "transform 120ms ease",
          "&:focus": {
            transform: "translateY(0)",
            outline: (theme) => `2px solid ${theme.palette.primary.main}`,
            outlineOffset: 2,
          },
        }}
      >
        Skip to main content
      </Link>
      <Box sx={{ display: "flex", minHeight: "100dvh" }}>
        <SideMenu user={user} onLogout={onLogout} />
        <AppNavbar user={user} onLogout={onLogout} />
        <Box
          component="main"
          id="main-content"
          ref={mainRef}
          tabIndex={-1}
          sx={{
            flexGrow: 1,
            backgroundColor: "background.default",
            overflow: "auto",
            position: "relative",
            outline: "none",
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
