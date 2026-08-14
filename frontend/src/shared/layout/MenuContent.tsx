import type { ReactElement } from "react";
import { useMemo, useState } from "react";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Collapse from "@mui/material/Collapse";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ExpandLess from "@mui/icons-material/ExpandLess";
import ExpandMore from "@mui/icons-material/ExpandMore";
import ManageAccountsRoundedIcon from "@mui/icons-material/ManageAccountsRounded";
import SettingsRoundedIcon from "@mui/icons-material/SettingsRounded";
import { Link, useLocation } from "react-router-dom";
import {
  filterDashboardNavigation,
  isApplicationsRoute,
  type DashboardNavChild,
  type DashboardNavEntry,
} from "./dashboardNavigation";

import { hasNavCapability } from "./dashboardNavCapabilities";

interface MenuContentProps {
  collapsed?: boolean;
  userRole?: string;
}

const navItemSx = {
  "& .MuiListItemText-primary": {
    fontSize: "0.875rem",
    fontWeight: 500,
    letterSpacing: "normal",
  },
};

const activeNavItemSx = {
  "&.Mui-selected": {
    backgroundColor: "action.selected",
    borderLeft: "2px solid",
    borderLeftColor: "primary.main",
    borderRadius: 0,
    "& .MuiListItemText-primary": {
      color: "primary.main",
      fontWeight: 500,
    },
    "& .MuiSvgIcon-root": {
      color: "primary.main",
    },
  },
};

function isPathActive(path: string, pathname: string, exact = false) {
  if (exact) return pathname === path;
  return pathname === path || pathname.startsWith(`${path}/`);
}

function isChildRouteActive(children: DashboardNavChild[], pathname: string) {
  return children.some((child) => isPathActive(child.path, pathname));
}

export default function MenuContent({
  collapsed = false,
  userRole,
}: MenuContentProps) {
  const location = useLocation();
  const sections = useMemo(
    () => filterDashboardNavigation(userRole),
    [userRole],
  );
  const applicationsActive = isApplicationsRoute(location.pathname, sections);
  const [applicationsExpanded, setApplicationsExpanded] =
    useState(applicationsActive);
  const [popupGroup, setPopupGroup] = useState<{
    anchor: HTMLElement;
    children: DashboardNavChild[];
    label: string;
  } | null>(null);

  const openApplications = applicationsActive || applicationsExpanded;

  const withTooltip = (label: string, node: ReactElement) =>
    collapsed ? (
      <Tooltip title={label} placement="right">
        {node}
      </Tooltip>
    ) : (
      node
    );

  const listButtonSx = collapsed
    ? {
        minHeight: 40,
        justifyContent: "center",
        px: 1.5,
        borderRadius: 0,
        ...navItemSx,
      }
    : { minHeight: 40, borderRadius: 0, ...navItemSx, ...activeNavItemSx };

  const listIconSx = collapsed
    ? { minWidth: 0, mr: 0, justifyContent: "center" }
    : { minWidth: 32 };

  const renderLeafLink = (item: DashboardNavEntry) =>
    withTooltip(
      item.text,
      <ListItemButton
        component={Link}
        to={item.path!}
        selected={isPathActive(item.path!, location.pathname, item.exact)}
        sx={listButtonSx}
      >
        <ListItemIcon sx={listIconSx}>{item.icon}</ListItemIcon>
        {!collapsed && <ListItemText primary={item.text} />}
      </ListItemButton>,
    );

  const renderExpandableGroup = (item: DashboardNavEntry) => {
    const children = item.children ?? [];
    const groupActive = isChildRouteActive(children, location.pathname);
    const expanded = item.text === "Applications" ? openApplications : groupActive;

    if (collapsed) {
      return (
        <>
          {withTooltip(
            item.text,
            <ListItemButton
              aria-label={`${item.text} menu`}
              aria-haspopup="menu"
              aria-expanded={popupGroup?.label === item.text}
              selected={groupActive}
              onClick={(event) =>
                setPopupGroup({
                  anchor: event.currentTarget,
                  children,
                  label: item.text,
                })
              }
              sx={listButtonSx}
            >
              <ListItemIcon sx={listIconSx}>{item.icon}</ListItemIcon>
            </ListItemButton>,
          )}
          <Menu
            anchorEl={popupGroup?.label === item.text ? popupGroup.anchor : null}
            open={popupGroup?.label === item.text}
            onClose={() => setPopupGroup(null)}
            anchorOrigin={{ vertical: "top", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "left" }}
          >
            {children.map((child) => (
              <MenuItem
                key={child.text}
                component={Link}
                to={child.path}
                selected={isPathActive(child.path, location.pathname)}
                onClick={() => setPopupGroup(null)}
              >
                <ListItemIcon sx={{ minWidth: 32 }}>{child.icon}</ListItemIcon>
                <ListItemText primary={child.text} />
              </MenuItem>
            ))}
          </Menu>
        </>
      );
    }

    return (
      <>
        <ListItemButton
          onClick={() => {
            if (item.text === "Applications") {
              setApplicationsExpanded((prev) => !prev);
            }
          }}
          selected={groupActive}
          aria-expanded={expanded}
          sx={listButtonSx}
        >
          <ListItemIcon sx={listIconSx}>{item.icon}</ListItemIcon>
          <ListItemText primary={item.text} />
          {expanded ? <ExpandLess /> : <ExpandMore />}
        </ListItemButton>
        <Collapse in={expanded} timeout="auto" unmountOnExit>
          <List component="div" disablePadding dense>
            {children.map((child) => (
              <ListItemButton
                key={child.text}
                component={Link}
                to={child.path}
                selected={isPathActive(child.path, location.pathname)}
                sx={{
                  pl: 4,
                  borderRadius: 0,
                  ...navItemSx,
                  ...activeNavItemSx,
                }}
              >
                <ListItemIcon sx={{ minWidth: 32 }}>{child.icon}</ListItemIcon>
                <ListItemText primary={child.text} />
              </ListItemButton>
            ))}
          </List>
        </Collapse>
      </>
    );
  };

  const renderEntry = (item: DashboardNavEntry) => {
    if (item.children?.length) return renderExpandableGroup(item);
    if (!item.path) return null;
    return renderLeafLink(item);
  };

  return (
    <Stack sx={{ flexGrow: 1, p: 1, justifyContent: "space-between" }}>
      <Stack spacing={1.5}>
        {sections.map((section) => (
          <Stack key={section.label} spacing={0.5}>
            {!collapsed ? (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ px: 1.5, pt: 0.5, fontWeight: 600, letterSpacing: 0.4 }}
              >
                {section.label}
              </Typography>
            ) : null}
            <List dense disablePadding>
              {section.entries.map((item) => (
                <ListItem key={`${section.label}-${item.text}`} disablePadding sx={{ display: "block" }}>
                  {renderEntry(item)}
                </ListItem>
              ))}
            </List>
          </Stack>
        ))}
      </Stack>

      <List dense>
        {hasNavCapability(userRole, "settings.account")
          ? withTooltip(
              "Team",
              <ListItemButton
                component={Link}
                to="/dashboard/account"
                selected={isPathActive("/dashboard/account", location.pathname)}
                sx={listButtonSx}
              >
                <ListItemIcon sx={listIconSx}>
                  <ManageAccountsRoundedIcon />
                </ListItemIcon>
                {!collapsed && <ListItemText primary="Team" />}
              </ListItemButton>,
            )
          : null}
        {hasNavCapability(userRole, "settings.workspace")
          ? withTooltip(
              "Settings",
              <ListItemButton
                component={Link}
                to="/dashboard/settings"
                selected={isPathActive("/dashboard/settings", location.pathname)}
                sx={listButtonSx}
              >
                <ListItemIcon sx={listIconSx}>
                  <SettingsRoundedIcon />
                </ListItemIcon>
                {!collapsed && <ListItemText primary="Settings" />}
              </ListItemButton>,
            )
          : null}
      </List>
    </Stack>
  );
}
