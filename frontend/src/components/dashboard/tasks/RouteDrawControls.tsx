import ChangeHistoryOutlinedIcon from "@mui/icons-material/ChangeHistoryOutlined";
import CropSquareOutlinedIcon from "@mui/icons-material/CropSquareOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import PentagonOutlinedIcon from "@mui/icons-material/PentagonOutlined";
import PanToolAltOutlinedIcon from "@mui/icons-material/PanToolAltOutlined";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import RadioButtonUncheckedOutlinedIcon from "@mui/icons-material/RadioButtonUncheckedOutlined";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import { IconButton, Paper, Stack, Tooltip } from "@mui/material";
import { useState, type ReactNode } from "react";

export type RouteDrawMode =
  | "none"
  | "point"
  | "polyline"
  | "polygon"
  | "rectangle"
  | "circle"
  | "triangle";
export type RouteDrawToolMode =
  | "none"
  | "point"
  | "polyline"
  | "polygon"
  | "rectangle"
  | "circle"
  | "triangle";

export function RouteDrawControls({
  mode,
  activeToolMode,
  onModeChange,
  onToolModeChange,
  onUndo,
  deleteLabel = "Delete selected drawing or latest waypoint",
  hasWaypoints,
}: {
  mode: RouteDrawMode;
  activeToolMode?: RouteDrawToolMode;
  onModeChange: (mode: RouteDrawMode) => void;
  onToolModeChange?: (mode: RouteDrawToolMode) => void;
  onUndo: () => void;
  deleteLabel?: string;
  hasWaypoints: boolean;
}) {
  const [activeTool, setActiveTool] = useState<RouteDrawToolMode>(activeToolMode ?? mode);
  const selectedTool =
    activeToolMode ??
    (mode === "polygon" && ["rectangle", "circle"].includes(activeTool)
      ? activeTool
      : mode);

  const tools: Array<{
    mode: RouteDrawToolMode;
    drawMode: RouteDrawMode;
    label: string;
    icon: ReactNode;
  }> = [
    {
      mode: "polygon",
      drawMode: "polygon",
      label: "Polygon",
      icon: <PentagonOutlinedIcon fontSize="small" />,
    },
    {
      mode: "triangle",
      drawMode: "polygon",
      label: "Triangle",
      icon: <ChangeHistoryOutlinedIcon fontSize="small" />,
    },
    {
      mode: "polyline",
      drawMode: "polyline",
      label: "Line",
      icon: <ShowChartIcon fontSize="small" />,
    },
    {
      mode: "point",
      drawMode: "point",
      label: "Point",
      icon: <PlaceOutlinedIcon fontSize="small" />,
    },
    {
      mode: "rectangle",
      drawMode: "polygon",
      label: "Rectangle",
      icon: <CropSquareOutlinedIcon fontSize="small" />,
    },
    {
      mode: "circle",
      drawMode: "polygon",
      label: "Circle",
      icon: <RadioButtonUncheckedOutlinedIcon fontSize="small" />,
    },
    {
      mode: "none",
      drawMode: "none",
      label: "Select",
      icon: <PanToolAltOutlinedIcon fontSize="small" />,
    },
  ];

  return (
    <Paper
      elevation={2}
      sx={{
        position: "absolute",
        left: 10,
        top: "50%",
        transform: "translateY(-50%)",
        zIndex: 1300,
        pointerEvents: "auto",
        p: 0.5,
        borderRadius: 1.5,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
      }}
    >
      <Stack direction="column" spacing={0.5}>
        {tools.map((tool) => {
          const selected = selectedTool === tool.mode;
          return (
            <Tooltip key={tool.mode} title={tool.label} placement="right" arrow>
              <span>
                <IconButton
                  size="small"
                  onClick={() => {
                    setActiveTool(tool.mode);
                    onModeChange(tool.drawMode);
                    if (onToolModeChange) onToolModeChange(tool.mode);
                  }}
                  sx={{
                    border: "1px solid",
                    borderColor: "divider",
                    bgcolor: selected ? "primary.main" : "background.paper",
                    color: selected ? "primary.contrastText" : "text.primary",
                    "&:hover": {
                      bgcolor: selected ? "primary.dark" : "action.hover",
                    },
                  }}
                >
                  {tool.icon}
                </IconButton>
              </span>
            </Tooltip>
          );
        })}

        <Tooltip title={deleteLabel} placement="right" arrow>
          <span>
            <IconButton
              size="small"
              color="error"
              onClick={onUndo}
              disabled={!hasWaypoints}
              sx={{
                border: "1px solid",
                borderColor: "divider",
                bgcolor: "background.paper",
                "&:hover": { bgcolor: "action.hover" },
              }}
            >
              <DeleteOutlineOutlinedIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
    </Paper>
  );
}
