import CropSquareOutlinedIcon from "@mui/icons-material/CropSquareOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import PanToolAltOutlinedIcon from "@mui/icons-material/PanToolAltOutlined";
import PentagonOutlinedIcon from "@mui/icons-material/PentagonOutlined";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import RadioButtonUncheckedOutlinedIcon from "@mui/icons-material/RadioButtonUncheckedOutlined";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import { IconButton, Paper, Stack, Tooltip, useMediaQuery, useTheme } from "@mui/material";
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
  /** Limit visible tools by mission mode (grid vs patrol vs geofence). */
  tools,
}: {
  mapEngine: MissionMapEngine;
  terraDrawMode: TerraDrawEditorMode;
  terraDrawReady: boolean;
  drawMode: DrawMode;
  deleteDisabled?: boolean;
  onToolSelect: (mode: TerraDrawToolMode) => void;
  onDelete: () => void;
  tools?: TerraDrawToolMode[];
}) {
  const theme = useTheme();
  const bottomSheet = useMediaQuery(theme.breakpoints.down("md"));
  const visibleTools = tools?.length
    ? DRAW_TOOLS.filter((tool) => tools.includes(tool.mode))
    : DRAW_TOOLS;

  return (
    <Paper
      elevation={2}
      role="toolbar"
      aria-label="Map draw tools"
      sx={{
        position: "absolute",
        zIndex: 1300,
        pointerEvents: "auto",
        p: 0.75,
        borderRadius: 1.5,
        border: "1px solid",
        borderColor: "rgba(255,255,255,0.55)",
        bgcolor: "rgba(18, 21, 26, 0.88)",
        boxShadow: "0 4px 18px rgba(0,0,0,0.45)",
        ...(bottomSheet
          ? {
              left: "50%",
              right: "auto",
              top: "auto",
              bottom: "calc(12px + env(safe-area-inset-bottom, 0px))",
              transform: "translateX(-50%)",
              maxWidth: "calc(100% - 24px)",
              overflowX: "auto",
            }
          : {
              left: 10,
              top: "50%",
              transform: "translateY(-50%)",
            }),
      }}
    >
      <Stack direction={bottomSheet ? "row" : "column"} spacing={0.5}>
        {visibleTools.map((tool) => {
          const selected =
            mapEngine !== "google"
              ? isFlatDrawToolSelected(drawMode, tool.mode)
              : terraDrawMode === tool.mode;

          return (
            <Tooltip
              key={tool.mode}
              title={tool.label}
              placement={bottomSheet ? "top" : "right"}
              arrow
            >
              <span>
                <IconButton
                  size="small"
                  onClick={() => onToolSelect(tool.mode)}
                  aria-label={tool.label}
                  aria-pressed={selected}
                  sx={{
                    minWidth: 48,
                    minHeight: 48,
                    border: "2px solid",
                    borderColor: selected ? "primary.main" : "common.white",
                    bgcolor: selected ? "primary.main" : "rgba(18, 21, 26, 0.82)",
                    color: selected ? "primary.contrastText" : "common.white",
                    boxShadow: selected
                      ? "0 0 0 2px #fff, 0 0 0 5px #3E6AE1"
                      : "0 0 0 1px rgba(0,0,0,0.55)",
                    "&:hover": {
                      bgcolor: selected ? "primary.dark" : "rgba(18, 21, 26, 0.95)",
                    },
                    "&:active": {
                      transform: "scale(0.96)",
                    },
                    "@media (prefers-reduced-motion: reduce)": {
                      "&:active": { transform: "none" },
                    },
                  }}
                >
                  {tool.icon}
                </IconButton>
              </span>
            </Tooltip>
          );
        })}

        <Tooltip
          title="Delete selected drawing"
          placement={bottomSheet ? "top" : "right"}
          arrow
        >
          <span>
            <IconButton
              size="small"
              color="error"
              aria-label="Delete selected drawing"
              onClick={onDelete}
              disabled={deleteDisabled ?? (mapEngine === "google" && !terraDrawReady)}
              sx={{
                minWidth: 48,
                minHeight: 48,
                border: "2px solid",
                borderColor: "rgba(255,255,255,0.7)",
                bgcolor: "rgba(18, 21, 26, 0.82)",
                color: "error.light",
                boxShadow: "0 0 0 1px rgba(0,0,0,0.55)",
                "&:hover": { bgcolor: "rgba(18, 21, 26, 0.95)" },
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
