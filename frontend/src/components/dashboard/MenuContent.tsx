import { useState } from "react";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Collapse from "@mui/material/Collapse";
import HomeRoundedIcon from "@mui/icons-material/HomeRounded";
import AssignmentRoundedIcon from "@mui/icons-material/AssignmentRounded";
import InsightsRoundedIcon from "@mui/icons-material/InsightsRounded";
import PrecisionManufacturingRoundedIcon from "@mui/icons-material/PrecisionManufacturingRounded";
import SettingsRoundedIcon from "@mui/icons-material/SettingsRounded";
import ExpandLess from "@mui/icons-material/ExpandLess";
import ExpandMore from "@mui/icons-material/ExpandMore";
import AgricultureIcon from "@mui/icons-material/Agriculture";
import GrassIcon from "@mui/icons-material/Grass";
import WaterDropIcon from '@mui/icons-material/WaterDrop';
import FlightTakeoffIcon from '@mui/icons-material/FlightTakeoff';
import { Link, useLocation } from "react-router-dom";
import TerrainIcon from '@mui/icons-material/Terrain';

const mainListItems = [
  { text: "Operations", icon: <HomeRoundedIcon />, path: "/dashboard" },
  {
    text: "Tasks",
    icon: <AssignmentRoundedIcon />,
//     path: "/dashboard/tasks",
    children: [
      { text: "Flight", icon: <FlightTakeoffIcon />, path: "/dashboard/tasks" },
      { text: "Terrain", icon: <TerrainIcon />, path: "/dashboard/terrain" },
//       { text: "Harvesting", icon: <AgricultureIcon />, path: "/dashboard/tasks/harvesting" },
//       { text: "Spraying", icon: <WaterDropIcon />, path: "/dashboard/tasks/spraying" },
    ]
  },
  { text: "Insights", icon: <InsightsRoundedIcon />, path: "/dashboard/insights" },
  { text: "Fleet", icon: <PrecisionManufacturingRoundedIcon />, path: "/dashboard/fleet" },
];

const secondaryListItems = [
  { text: "Settings", icon: <SettingsRoundedIcon />, path: "/dashboard/settings" },
];

export default function MenuContent() {
  const location = useLocation();
  const [openTasks, setOpenTasks] = useState(() => {
    // Auto-expand if any task route is active
    return location.pathname.startsWith("/dashboard/tasks");
  });

  const handleTasksClick = () => {
    setOpenTasks(!openTasks);
  };

  return (
    <Stack sx={{ flexGrow: 1, p: 1, justifyContent: "space-between" }}>
      <List dense>
        {mainListItems.map((item) => (
          <div key={item.text}>
            <ListItem disablePadding sx={{ display: "block" }}>
              {item.children ? (
                // Item with children (expandable)
                <ListItemButton
                  onClick={handleTasksClick}
                  selected={location.pathname.startsWith(item.path)}
                >
                  <ListItemIcon>{item.icon}</ListItemIcon>
                  <ListItemText primary={item.text} />
                  {openTasks ? <ExpandLess /> : <ExpandMore />}
                </ListItemButton>
              ) : (
                // Regular item (no children)
                <ListItemButton
                  component={Link}
                  to={item.path}
                  selected={
                    location.pathname === item.path ||
                    location.pathname.startsWith(`${item.path}/`)
                  }
                >
                  <ListItemIcon>{item.icon}</ListItemIcon>
                  <ListItemText primary={item.text} />
                </ListItemButton>
              )}
            </ListItem>

            {/* Render children if they exist */}
            {item.children && (
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
                      sx={{ pl: 4 }} // Indent children
                    >
                      <ListItemIcon sx={{ minWidth: 36 }}>{child.icon}</ListItemIcon>
                      <ListItemText primary={child.text} />
                    </ListItemButton>
                  ))}
                </List>
              </Collapse>
            )}
          </div>
        ))}
      </List>

      <List dense>
        {secondaryListItems.map((item) => (
          <ListItem key={item.text} disablePadding sx={{ display: "block" }}>
            <ListItemButton
              component={Link}
              to={item.path}
              selected={
                location.pathname === item.path ||
                location.pathname.startsWith(`${item.path}/`)
              }
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Stack>
  );
}