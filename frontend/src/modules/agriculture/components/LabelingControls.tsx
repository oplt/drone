import {
  ArrowBack,
  ArrowForward,
  CenterFocusStrong,
  CheckCircle,
  CropSquare,
  FitScreen,
  Fullscreen,
  FullscreenExit,
  HelpOutline,
  PanTool,
  TouchApp,
  ZoomIn,
  ZoomOut,
} from "@mui/icons-material";
import {
  Box,
  Button,
  Divider,
  IconButton,
  Menu,
  MenuItem,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import type { AnnotationCanvasHandle, AnnotationTool } from "./AnnotationCanvas";
import type { LabelingSaveState } from "../hooks/useLabelingPersistence";
import { labelingSaveToIndicator } from "../../../shared/ui/saveIndicatorState";
import { SaveIndicator } from "../../../shared/ui/SaveIndicator";

export function LabelingHeader({
  title,
  reviewed,
  total,
  saveState,
  expanded,
  toggleExpanded,
  showHelp,
  close,
}: {
  title: string;
  reviewed: number;
  total: number;
  saveState: LabelingSaveState;
  expanded: boolean;
  toggleExpanded: () => void;
  showHelp: (target: HTMLElement) => void;
  close: () => void;
}) {
  return (
    <Stack direction="row" alignItems="center" justifyContent="space-between" px={2} py={1}>
      <Box>
        <Typography variant="h6">{title}</Typography>
        <Typography variant="caption" color="text.secondary">{reviewed} / {total} reviewed</Typography>
      </Box>
      <Stack direction="row" alignItems="center" spacing={1}>
        <SaveIndicator state={labelingSaveToIndicator(saveState)} />
        <Tooltip title="Keyboard shortcuts">
          <IconButton
            aria-label="Show keyboard shortcuts"
            aria-haspopup="menu"
            onClick={(event) => showHelp(event.currentTarget)}
          >
            <HelpOutline />
          </IconButton>
        </Tooltip>
        <Tooltip title={expanded ? "Exit expanded view" : "Expanded view"}>
          <IconButton
            aria-label={expanded ? "Exit expanded view" : "Enter expanded view"}
            aria-pressed={expanded}
            onClick={toggleExpanded}
          >
            {expanded ? <FullscreenExit /> : <Fullscreen />}
          </IconButton>
        </Tooltip>
        <Button onClick={close}>Close</Button>
      </Stack>
    </Stack>
  );
}

export function LabelingToolbar({
  tool,
  zoom,
  canvas,
  setTool,
}: {
  tool: AnnotationTool;
  zoom: number;
  canvas: React.RefObject<AnnotationCanvasHandle | null>;
  setTool: (tool: AnnotationTool) => void;
}) {
  return (
    <Stack
      direction="row"
      alignItems="center"
      spacing={0.5}
      px={1}
      py={0.5}
      role="toolbar"
      aria-label="Annotation tools"
    >
      <Tooltip title="Select (V)">
        <IconButton
          color={tool === "select" ? "primary" : "default"}
          aria-label="Select tool (V)"
          aria-pressed={tool === "select"}
          onClick={() => setTool("select")}
        >
          <TouchApp />
        </IconButton>
      </Tooltip>
      <Tooltip title="Draw box (B)">
        <IconButton
          color={tool === "draw" ? "primary" : "default"}
          aria-label="Draw box tool (B)"
          aria-pressed={tool === "draw"}
          onClick={() => setTool("draw")}
        >
          <CropSquare />
        </IconButton>
      </Tooltip>
      <Tooltip title="Pan (hold Space)">
        <IconButton
          color={tool === "pan" ? "primary" : "default"}
          aria-label="Pan tool (hold Space)"
          aria-pressed={tool === "pan"}
          onClick={() => setTool("pan")}
        >
          <PanTool />
        </IconButton>
      </Tooltip>
      <Divider orientation="vertical" flexItem />
      <Tooltip title="Zoom out">
        <IconButton aria-label="Zoom out" onClick={() => canvas.current?.zoomOut()}>
          <ZoomOut />
        </IconButton>
      </Tooltip>
      <Typography variant="body2" width={52} textAlign="center" aria-live="polite">
        {Math.round(zoom * 100)}%
      </Typography>
      <Tooltip title="Zoom in">
        <IconButton aria-label="Zoom in" onClick={() => canvas.current?.zoomIn()}>
          <ZoomIn />
        </IconButton>
      </Tooltip>
      <Tooltip title="Fit image (F)">
        <IconButton aria-label="Fit image (F)" onClick={() => canvas.current?.fit()}>
          <FitScreen />
        </IconButton>
      </Tooltip>
      <Tooltip title="Reset view">
        <IconButton aria-label="Reset view" onClick={() => canvas.current?.fit()}>
          <CenterFocusStrong />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}

export function LabelingFooter({
  position,
  total,
  reviewed,
  navigate,
  toggleReviewed,
}: {
  position: number;
  total: number;
  reviewed: boolean;
  navigate: (direction: -1 | 1) => void;
  toggleReviewed: () => void;
}) {
  return (
    <Stack direction="row" alignItems="center" justifyContent="space-between" p={1}>
      <Button startIcon={<ArrowBack />} disabled={position === 0} onClick={() => navigate(-1)}>Previous</Button>
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="body2">{position + 1} / {total}</Typography>
        <Button variant={reviewed ? "outlined" : "contained"} color={reviewed ? "success" : "primary"} startIcon={<CheckCircle />} onClick={toggleReviewed}>
          {reviewed ? "Reviewed" : "Mark reviewed"}
        </Button>
      </Stack>
      <Button endIcon={<ArrowForward />} disabled={position + 1 >= total} onClick={() => navigate(1)}>Next</Button>
    </Stack>
  );
}

export function LabelingShortcutMenu({
  anchor,
  close,
}: {
  anchor: HTMLElement | null;
  close: () => void;
}) {
  const shortcuts = [
    "B Draw box · V Select · Space Pan",
    "A / ← Previous · D / → Next",
    "F or 0 Fit · + / − Zoom",
    "Delete Remove · Esc Cancel",
    "Ctrl/Cmd+S Save · 1–9 Select class",
  ];
  return (
    <Menu
      anchorEl={anchor}
      open={Boolean(anchor)}
      onClose={close}
      MenuListProps={{
        "aria-label": "Keyboard shortcuts",
        autoFocusItem: true,
        dense: true,
      }}
    >
      {shortcuts.map((text) => (
        <MenuItem key={text} disabled sx={{ opacity: "1 !important", color: "text.primary" }}>
          {text}
        </MenuItem>
      ))}
      <MenuItem onClick={close} autoFocus>
        Close shortcuts
      </MenuItem>
    </Menu>
  );
}
