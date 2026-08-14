import * as React from "react";
import { styled } from "@mui/material/styles";
import AppBar from "@mui/material/AppBar";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import MuiToolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import BugReportRoundedIcon from "@mui/icons-material/BugReportRounded";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import NotificationsRoundedIcon from "@mui/icons-material/NotificationsRounded";
import { Link as RouterLink, useLocation } from "react-router-dom";
import SideMenuMobile from "./SideMenuMobile";
import MenuButton from "./MenuButton";
import TelemetryLinkChip from "./TelemetryLinkChip";
import { buildBreadcrumbTrail } from "./breadcrumbTrail";
import { useSystemLogs } from "./systemLogsContext";
import ColorModeIconDropdown from "../theme/ColorModeIconDropdown";
import { useAlertCenter } from "../../modules/alerts";

import type { ShellUser } from "./types";

const Toolbar = styled(MuiToolbar)({
  width: "100%",
  padding: "12px 16px",
  display: "flex",
  flexDirection: "column",
  alignItems: "start",
  justifyContent: "center",
  gap: "12px",
  flexShrink: 0,
});

type AppNavbarProps = {
  user: ShellUser;
  onLogout: () => void | Promise<void>;
};

export default function AppNavbar({ user, onLogout }: AppNavbarProps) {
  const [open, setOpen] = React.useState(false);
  const [crumbAnchor, setCrumbAnchor] = React.useState<null | HTMLElement>(null);
  const { openCount, setDrawerOpen } = useAlertCenter();
  const { setOpen: setLogsOpen, criticalCount } = useSystemLogs();
  const { pathname } = useLocation();
  const crumbs = buildBreadcrumbTrail(pathname);
  const currentCrumb = crumbs[crumbs.length - 1];

  const toggleDrawer = (nextOpen: boolean) => () => {
    setOpen(nextOpen);
  };

  return (
    <AppBar
      position="fixed"
      sx={{
        display: { xs: "block", md: "none" },
        boxShadow: 0,
        bgcolor: "transparent",
        backgroundImage: "none",
        top: "var(--template-frame-height, 0px)",
      }}
    >
      <Toolbar variant="regular">
        <Stack
          direction="row"
          sx={{
            alignItems: "center",
            width: "100%",
            gap: 0.5,
            px: 1.5,
            py: 1,
            bgcolor: "background.paper",
            backdropFilter: "blur(8px)",
          }}
        >
          <Stack spacing={0.25} sx={{ mr: "auto", minWidth: 0 }}>
            <Typography
              sx={{
                fontSize: "0.875rem",
                fontWeight: 500,
                letterSpacing: "0.12em",
                color: "text.primary",
              }}
            >
              drone ops
            </Typography>
            <Typography
              variant="caption"
              noWrap
              sx={{ color: "text.secondary", maxWidth: 140 }}
            >
              {currentCrumb?.label ?? "Overview"}
            </Typography>
          </Stack>
          <IconButton
            size="small"
            aria-label="Open breadcrumbs"
            onClick={(event) => setCrumbAnchor(event.currentTarget)}
          >
            <MoreVertIcon fontSize="small" />
          </IconButton>
          <Menu
            anchorEl={crumbAnchor}
            open={Boolean(crumbAnchor)}
            onClose={() => setCrumbAnchor(null)}
          >
            {crumbs.map((crumb) => (
              <MenuItem
                key={crumb.to}
                component={RouterLink}
                to={crumb.to}
                selected={crumb.current}
                onClick={() => setCrumbAnchor(null)}
              >
                {crumb.label}
              </MenuItem>
            ))}
          </Menu>
          <TelemetryLinkChip compact />
          <MenuButton
            showBadge={openCount > 0}
            aria-label="Open notifications"
            onClick={() => setDrawerOpen(true)}
          >
            <NotificationsRoundedIcon />
          </MenuButton>
          <MenuButton
            showBadge={criticalCount > 0}
            aria-label="Open system events"
            onClick={() => setLogsOpen(true)}
          >
            <BugReportRoundedIcon />
          </MenuButton>
          <ColorModeIconDropdown />
          <MenuButton aria-label="Open menu" onClick={toggleDrawer(true)}>
            <MenuRoundedIcon />
          </MenuButton>
          <SideMenuMobile
            open={open}
            toggleDrawer={toggleDrawer}
            user={user}
            onLogout={onLogout}
          />
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
