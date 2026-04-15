import React from "react";
import { Outlet, useNavigate } from "react-router-dom";
import CssBaseline from "@mui/material/CssBaseline";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import AppNavbar from "../../components/dashboard/AppNavbar";
import SideMenu from "../../components/dashboard/SideMenu";
import AppTheme from "../../components/shared-theme/AppTheme";
import PageLoader from "../../components/shared/PageLoader";
import { getToken, clearToken } from "../../auth";
import {
  chartsCustomizations,
  dataGridCustomizations,
  datePickersCustomizations,
} from "../../components/theme/customizations";
import { AlertCenterProvider } from "../../contexts/AlertCenterContext";

type User = {
  id: number;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  role?: string | null;
};

const xThemeComponents = {
  ...chartsCustomizations,
  ...dataGridCustomizations,
  ...datePickersCustomizations,
};

export default function Dashboard(props: { disableCustomTheme?: boolean }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [authChecked, setAuthChecked] = React.useState(false);
  const navigate = useNavigate();
  const API_BASE_RAW = import.meta.env.VITE_API_BASE_URL ?? "";
  const API_BASE_CLEAN = (API_BASE_RAW || "http://localhost:8000").replace(/\/$/, "");

  React.useEffect(() => {
    const token = getToken();
    if (!token) {
      navigate("/signin", { replace: true });
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    const fetchMe = (signal: AbortSignal) =>
      fetch(`${API_BASE_CLEAN}/auth/me`, {
        credentials: "include",
        signal,
      });

    fetchMe(controller.signal)
      .then(async (r) => {
        if (r.status === 401) {
          const refreshRes = await fetch(`${API_BASE_CLEAN}/auth/refresh`, {
            method: "POST",
            credentials: "include",
          });
          if (!refreshRes.ok) throw new Error("unauthorized");
          return fetchMe(controller.signal);
        }
        return r;
      })
      .then(async (r) => {
        if (!r.ok) {
          if (r.status === 401 || r.status === 403) {
            throw new Error("unauthorized");
          }
          const text = await r.text().catch(() => "");
          throw new Error(text || `HTTP ${r.status}`);
        }
        return r.json();
      })
      .then((nextUser) => {
        if (cancelled) return;
        setUser(nextUser);
        setAuthChecked(true);
      })
      .catch((error) => {
        if (cancelled) return;
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (error instanceof Error && error.message === "unauthorized") {
          clearToken();
          navigate("/signin", { replace: true });
          return;
        }
        console.warn("Failed to load user profile:", error);
        setAuthChecked(true);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [API_BASE_CLEAN, navigate]);

  if (!authChecked) {
    return <PageLoader fullScreen title="Loading console" subtitle="Checking access and preparing your operations workspace." />;
  }

  return (
    <AppTheme {...props} themeComponents={xThemeComponents}>
      <CssBaseline enableColorScheme />
      <Box sx={{ display: "flex", minHeight: "100dvh" }}>
        <SideMenu user={user} />
        <AppNavbar user={user} />
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            backgroundColor: "background.default",
            overflow: "auto",
            position: "relative",
          }}
        >
          <AlertCenterProvider>
            <Stack
              spacing={2}
              sx={{
                alignItems: "center",
                px: { xs: 2, md: 3 },
                pb: 5,
                pt: { xs: 9, md: 2.5 },
                position: "relative",
                zIndex: 1,
              }}
            >
              <Outlet />
            </Stack>
          </AlertCenterProvider>
        </Box>
      </Box>
    </AppTheme>
  );
}
