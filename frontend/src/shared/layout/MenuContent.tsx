import type { ReactElement, ReactNode } from "react";
import { useState } from "react";
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
import HomeRoundedIcon from "@mui/icons-material/HomeRounded";
import AssignmentRoundedIcon from "@mui/icons-material/AssignmentRounded";
import InsightsRoundedIcon from "@mui/icons-material/InsightsRounded";
import PrecisionManufacturingRoundedIcon from "@mui/icons-material/PrecisionManufacturingRounded";
import SettingsRoundedIcon from "@mui/icons-material/SettingsRounded";
import ExpandLess from "@mui/icons-material/ExpandLess";
import ExpandMore from "@mui/icons-material/ExpandMore";
import SportsEsportsRoundedIcon from "@mui/icons-material/SportsEsportsRounded";
import ManageAccountsRoundedIcon from "@mui/icons-material/ManageAccountsRounded";
import PhotoCameraRoundedIcon from "@mui/icons-material/PhotoCameraRounded";
import EmojiNatureRoundedIcon from "@mui/icons-material/EmojiNatureRounded";
import AgricultureIcon from "@mui/icons-material/Agriculture";
import VisibilityRoundedIcon from "@mui/icons-material/VisibilityRounded";
import WarehouseRoundedIcon from "@mui/icons-material/WarehouseRounded";
import AdminPanelSettingsRoundedIcon from "@mui/icons-material/AdminPanelSettingsRounded";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import QueryStatsRoundedIcon from "@mui/icons-material/QueryStatsRounded";
import MapRoundedIcon from "@mui/icons-material/MapRounded";
import VideocamRoundedIcon from "@mui/icons-material/VideocamRounded";
import SecurityRoundedIcon from "@mui/icons-material/SecurityRounded";
import { Link, useLocation } from "react-router-dom";

interface MenuChildItem {
  text: string;
  icon: ReactNode;
  path: string;
}

interface MenuItemDef {
  text: string;
  icon: ReactNode;
  path?: string;
  /** When true, parent path matches only exactly (Operations hub). */
  exact?: boolean;
  /** Parent expands children only; never navigates. */
  expandOnly?: boolean;
  children?: MenuChildItem[];
}

interface MenuContentProps {
  collapsed?: boolean;
  userRole?: string;
}

const mainListItems: MenuItemDef[] = [
  { text: "Operations", icon: <HomeRoundedIcon />, path: "/dashboard", exact: true },
  {
    text: "Tasks",
    icon: <AssignmentRoundedIcon />,
    expandOnly: true,
    children: [
      {
        text: "Field Survey",
        icon: <MapRoundedIcon />,
        path: "/dashboard/field",
      },
      {
        text: "Agriculture Fields",
        icon: <AgricultureIcon />,
        path: "/dashboard/agriculture/fields",
      },
      {
        text: "Vision Models",
        icon: <VisibilityRoundedIcon />,
        path: "/dashboard/agriculture/vision-models",
      },
      {
        text: "Property Patrol",
        icon: <SecurityRoundedIcon />,
        path: "/dashboard/property-patrol",
      },
      {
        text: "Warehouse",
        icon: <WarehouseRoundedIcon />,
        path: "/dashboard/warehouse",
      },
      {
        text: "Photogrammetry",
        icon: <PhotoCameraRoundedIcon />,
        path: "/dashboard/photogrammetry",
      },
      {
        text: "Animal Farm",
        icon: <EmojiNatureRoundedIcon />,
        path: "/dashboard/animalfarm",
      },
      {
        text: "Controlled Flight",
        icon: <SportsEsportsRoundedIcon />,
        path: "/dashboard/controlled",
      },
      {
        text: "Video Analysis",
        icon: <VideocamRoundedIcon />,
        path: "/dashboard/video-analysis",
      },
    ],
  },
  {
    text: "Insights",
    icon: <InsightsRoundedIcon />,
    path: "/dashboard/insights",
  },
  {
    text: "Observability",
    icon: <QueryStatsRoundedIcon />,
    path: "/dashboard/observability",
  },
  {
    text: "Fleet",
    icon: <PrecisionManufacturingRoundedIcon />,
    path: "/dashboard/fleet",
  },
  {
    text: "Templates",
    icon: <ContentCopyRoundedIcon />,
    path: "/dashboard/templates",
  },
];

const secondaryListItems: MenuItemDef[] = [
  {
    text: "Account",
    icon: <ManageAccountsRoundedIcon />,
    path: "/dashboard/account",
  },
  {
    text: "Settings",
    icon: <SettingsRoundedIcon />,
    path: "/dashboard/settings",
  },
];

const tasksChildren =
  mainListItems.find((item) => item.text === "Tasks")?.children ?? [];

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

export default function MenuContent({
  collapsed = false,
  userRole,
}: MenuContentProps) {
  const location = useLocation();
  const [tasksMenuAnchor, setTasksMenuAnchor] = useState<null | HTMLElement>(null);

  const isSelected = (item: MenuItemDef, pathname: string) => {
    if (!item.path) return false;
    if (item.exact) return pathname === item.path;
    return pathname === item.path || pathname.startsWith(`${item.path}/`);
  };

  const isTaskRoute = (pathname: string) =>
    tasksChildren.some(
      (child) =>
        pathname === child.path || pathname.startsWith(`${child.path}/`),
    );

  const taskRouteActive = isTaskRoute(location.pathname);
  const [tasksExpanded, setTasksExpanded] = useState(taskRouteActive);
  const openTasks = taskRouteActive || tasksExpanded;

  const handleTasksClick = () => {
    setTasksExpanded((prev) => !prev);
  };

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

  return (
    <Stack sx={{ flexGrow: 1, p: 1, justifyContent: "space-between" }}>
      <List dense>
        {mainListItems.map((item) => (
          <ListItem key={item.text} disablePadding sx={{ display: "block" }}>
            {item.children && collapsed ? (
              <>
                {withTooltip(
                  item.text,
                  <ListItemButton
                    aria-label={`${item.text} menu`}
                    aria-haspopup="menu"
                    aria-expanded={Boolean(tasksMenuAnchor)}
                    selected={isTaskRoute(location.pathname)}
                    onClick={(event) => setTasksMenuAnchor(event.currentTarget)}
                    sx={listButtonSx}
                  >
                    <ListItemIcon sx={listIconSx}>{item.icon}</ListItemIcon>
                  </ListItemButton>,
                )}
                <Menu
                  anchorEl={tasksMenuAnchor}
                  open={Boolean(tasksMenuAnchor)}
                  onClose={() => setTasksMenuAnchor(null)}
                  anchorOrigin={{ vertical: "top", horizontal: "right" }}
                  transformOrigin={{ vertical: "top", horizontal: "left" }}
                >
                  {item.children.map((child) => (
                    <MenuItem
                      key={child.text}
                      component={Link}
                      to={child.path}
                      selected={
                        location.pathname === child.path ||
                        location.pathname.startsWith(`${child.path}/`)
                      }
                      onClick={() => setTasksMenuAnchor(null)}
                    >
                      <ListItemIcon sx={{ minWidth: 32 }}>{child.icon}</ListItemIcon>
                      <ListItemText primary={child.text} />
                    </MenuItem>
                  ))}
                </Menu>
              </>
            ) : item.children ? (
              <>
                <ListItemButton
                  onClick={handleTasksClick}
                  selected={isTaskRoute(location.pathname)}
                  aria-expanded={openTasks}
                  sx={listButtonSx}
                >
                  <ListItemIcon sx={listIconSx}>{item.icon}</ListItemIcon>
                  <ListItemText primary={item.text} />
                  {openTasks ? <ExpandLess /> : <ExpandMore />}
                </ListItemButton>
                <Collapse in={openTasks} timeout="auto" unmountOnExit>
                  <List component="div" disablePadding dense>
                    {item.children.map((child) => (
                      <ListItemButton
                        key={child.text}
                        component={Link}
                        to={child.path}
                        selected={
                          location.pathname === child.path ||
                          location.pathname.startsWith(`${child.path}/`)
                        }
                        sx={{
                          pl: 4,
                          borderRadius: 0,
                          ...navItemSx,
                          ...activeNavItemSx,
                        }}
                      >
                        <ListItemIcon sx={{ minWidth: 32 }}>
                          {child.icon}
                        </ListItemIcon>
                        <ListItemText primary={child.text} />
                      </ListItemButton>
                    ))}
                  </List>
                </Collapse>
              </>
            ) : (
              withTooltip(
                item.text,
                <ListItemButton
                  component={Link}
                  to={item.path!}
                  selected={isSelected(item, location.pathname)}
                  sx={listButtonSx}
                >
                  <ListItemIcon sx={listIconSx}>{item.icon}</ListItemIcon>
                  {!collapsed && <ListItemText primary={item.text} />}
                </ListItemButton>,
              )
            )}
          </ListItem>
        ))}
      </List>

      <List dense>
        {userRole === "admin" &&
          withTooltip(
            "Admin",
            <ListItemButton
              component={Link}
              to="/dashboard/admin"
              selected={location.pathname.startsWith("/dashboard/admin")}
              sx={listButtonSx}
            >
              <ListItemIcon sx={listIconSx}>
                <AdminPanelSettingsRoundedIcon />
              </ListItemIcon>
              {!collapsed && <ListItemText primary="Admin" />}
            </ListItemButton>,
          )}
        {secondaryListItems.map((item) => (
          <ListItem key={item.text} disablePadding sx={{ display: "block" }}>
            {withTooltip(
              item.text,
              <ListItemButton
                component={Link}
                to={item.path!}
                selected={
                  location.pathname === item.path ||
                  location.pathname.startsWith(`${item.path}/`)
                }
                sx={listButtonSx}
              >
                <ListItemIcon sx={listIconSx}>{item.icon}</ListItemIcon>
                {!collapsed && <ListItemText primary={item.text} />}
              </ListItemButton>,
            )}
          </ListItem>
        ))}
      </List>
    </Stack>
  );
}
