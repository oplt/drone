import CropSquareOutlinedIcon from "@mui/icons-material/CropSquareOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import PanToolAltOutlinedIcon from "@mui/icons-material/PanToolAltOutlined";
import PentagonOutlinedIcon from "@mui/icons-material/PentagonOutlined";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import RadioButtonUncheckedOutlinedIcon from "@mui/icons-material/RadioButtonUncheckedOutlined";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import { IconButton, Paper, Stack, Tooltip } from "@mui/material";
import type { ReactNode } from "react";
import {
  isFlatDrawToolSelected,
  type DrawMode,
  type MissionMapEngine,
  type TerraDrawEditorMode,
  type TerraDrawToolMode,
} from "../../maps";

const DRAW_TOOLS: Array<{
  mode: TerraDrawToolMode;
  label: string;
  icon: ReactNode;
}> = [
  { mode: "polygon", label: "Polygon", icon: <PentagonOutlinedIcon fontSize="small" /> },
  { mode: "linestring", label: "Line", icon: <ShowChartIcon fontSize="small" /> },
  { mode: "point", label: "Point", icon: <PlaceOutlinedIcon fontSize="small" /> },
  {
    mode: "rectangle",
    label: "Rectangle",
    icon: <CropSquareOutlinedIcon fontSize="small" />,
  },
  {
    mode: "circle",
    label: "Circle",
    icon: <RadioButtonUncheckedOutlinedIcon fontSize="small" />,
  },
  { mode: "select", label: "Select", icon: <PanToolAltOutlinedIcon fontSize="small" /> },
];

export function MapDrawToolsOverlay({
  mapEngine,
  terraDrawMode,
  terraDrawReady,
  drawMode,
  deleteDisabled,
  onToolSelect,
  onDelete,
}: {
  mapEngine: MissionMapEngine;
  terraDrawMode: TerraDrawEditorMode;
  terraDrawReady: boolean;
  drawMode: DrawMode;
  deleteDisabled?: boolean;
  onToolSelect: (mode: TerraDrawToolMode) => void;
  onDelete: () => void;
}) {
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
        {DRAW_TOOLS.map((tool) => {
          const selected =
            mapEngine !== "google"
              ? isFlatDrawToolSelected(drawMode, tool.mode)
              : terraDrawMode === tool.mode;

          return (
            <Tooltip key={tool.mode} title={tool.label} placement="right" arrow>
              <span>
                <IconButton
                  size="small"
                  onClick={() => onToolSelect(tool.mode)}
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

        <Tooltip title="Delete selected drawing" placement="right" arrow>
          <span>
            <IconButton
              size="small"
              color="error"
              onClick={onDelete}
              disabled={deleteDisabled ?? (mapEngine === "google" && !terraDrawReady)}
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
