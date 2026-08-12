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
  CircularProgress,
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
      <Stack direction="row" alignItems="center" spacing={1} aria-live="polite">
        {saveState === "saving" ? <CircularProgress size={16} /> : null}
        {saveState === "saved" ? <CheckCircle color="success" fontSize="small" /> : null}
        <Typography variant="body2">
          {saveState === "saving" ? "Saving…" : saveState === "failed" ? "Save failed" : "Saved"}
        </Typography>
        <Tooltip title="Keyboard shortcuts">
          <IconButton onClick={(event) => showHelp(event.currentTarget)}><HelpOutline /></IconButton>
        </Tooltip>
        <Tooltip title={expanded ? "Exit expanded view" : "Expanded view"}>
          <IconButton onClick={toggleExpanded}>{expanded ? <FullscreenExit /> : <Fullscreen />}</IconButton>
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
    <Stack direction="row" alignItems="center" spacing={0.5} px={1} py={0.5}>
      <Tooltip title="Select (V)"><IconButton color={tool === "select" ? "primary" : "default"} onClick={() => setTool("select")}><TouchApp /></IconButton></Tooltip>
      <Tooltip title="Draw box (B)"><IconButton color={tool === "draw" ? "primary" : "default"} onClick={() => setTool("draw")}><CropSquare /></IconButton></Tooltip>
      <Tooltip title="Pan (hold Space)"><IconButton color={tool === "pan" ? "primary" : "default"} onClick={() => setTool("pan")}><PanTool /></IconButton></Tooltip>
      <Divider orientation="vertical" flexItem />
      <Tooltip title="Zoom out"><IconButton onClick={() => canvas.current?.zoomOut()}><ZoomOut /></IconButton></Tooltip>
      <Typography variant="body2" width={52} textAlign="center">{Math.round(zoom * 100)}%</Typography>
      <Tooltip title="Zoom in"><IconButton onClick={() => canvas.current?.zoomIn()}><ZoomIn /></IconButton></Tooltip>
      <Tooltip title="Fit image (F)"><IconButton onClick={() => canvas.current?.fit()}><FitScreen /></IconButton></Tooltip>
      <Tooltip title="Reset view"><IconButton onClick={() => canvas.current?.fit()}><CenterFocusStrong /></IconButton></Tooltip>
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
    <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={close}>
      {shortcuts.map((text) => <MenuItem key={text}>{text}</MenuItem>)}
    </Menu>
  );
}
