import type { ReactNode } from "react";
import type { IconButtonProps } from "@mui/material";
import { CircularProgress, IconButton, Tooltip } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RefreshIcon from "@mui/icons-material/Refresh";
import CheckIcon from "@mui/icons-material/Check";
import UpgradeIcon from "@mui/icons-material/Upgrade";
import DeleteIcon from "@mui/icons-material/Delete";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import PauseIcon from "@mui/icons-material/Pause";
import StopIcon from "@mui/icons-material/Stop";
import ExploreIcon from "@mui/icons-material/Explore";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import MapIcon from "@mui/icons-material/Map";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close";
import CenterFocusStrongIcon from "@mui/icons-material/CenterFocusStrong";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import ReplayIcon from "@mui/icons-material/Replay";
import UndoIcon from "@mui/icons-material/Undo";
import LinkIcon from "@mui/icons-material/Link";
import FlightTakeoffIcon from "@mui/icons-material/FlightTakeoff";
import KeyboardIcon from "@mui/icons-material/Keyboard";
import FactCheckIcon from "@mui/icons-material/FactCheck";
import MapOutlinedIcon from "@mui/icons-material/MapOutlined";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import LogoutIcon from "@mui/icons-material/Logout";

export type ActionIconVariant =
  | "add"
  | "refresh"
  | "check"
  | "upgrade"
  | "delete"
  | "play"
  | "pause"
  | "resume"
  | "stop"
  | "abort"
  | "explore"
  | "upload"
  | "open"
  | "map"
  | "search"
  | "close"
  | "focus"
  | "visibility"
  | "visibility-off"
  | "retry"
  | "connect"
  | "takeoff"
  | "keyboard"
  | "preflight"
  | "plan"
  | "undo"
  | "download"
  | "logout";

const ACTION_ICONS: Record<ActionIconVariant, ReactNode> = {
  add: <AddIcon fontSize="small" />,
  refresh: <RefreshIcon fontSize="small" />,
  check: <CheckIcon fontSize="small" />,
  upgrade: <UpgradeIcon fontSize="small" />,
  delete: <DeleteIcon fontSize="small" />,
  play: <PlayArrowIcon fontSize="small" />,
  pause: <PauseIcon fontSize="small" />,
  resume: <PlayArrowIcon fontSize="small" />,
  stop: <StopIcon fontSize="small" />,
  abort: <StopIcon fontSize="small" />,
  explore: <ExploreIcon fontSize="small" />,
  upload: <CloudUploadIcon fontSize="small" />,
  open: <OpenInNewIcon fontSize="small" />,
  map: <MapIcon fontSize="small" />,
  search: <SearchIcon fontSize="small" />,
  close: <CloseIcon fontSize="small" />,
  focus: <CenterFocusStrongIcon fontSize="small" />,
  visibility: <VisibilityIcon fontSize="small" />,
  "visibility-off": <VisibilityOffIcon fontSize="small" />,
  retry: <ReplayIcon fontSize="small" />,
  connect: <LinkIcon fontSize="small" />,
  takeoff: <FlightTakeoffIcon fontSize="small" />,
  keyboard: <KeyboardIcon fontSize="small" />,
  preflight: <FactCheckIcon fontSize="small" />,
  plan: <MapOutlinedIcon fontSize="small" />,
  undo: <UndoIcon fontSize="small" />,
  download: <FileDownloadIcon fontSize="small" />,
  logout: <LogoutIcon fontSize="small" />,
};

export type ActionIconButtonProps = {
  variant: ActionIconVariant;
  title: string;
  loading?: boolean;
  disabled?: boolean;
  onClick?: IconButtonProps["onClick"];
  color?: IconButtonProps["color"];
  size?: IconButtonProps["size"];
  wrap?: boolean;
  component?: React.ElementType;
  to?: string;
  href?: string;
  type?: "button" | "submit" | "reset";
} & Omit<IconButtonProps, "children" | "onClick" | "color" | "size" | "disabled">;

export function ActionIconButton({
  variant,
  title,
  loading = false,
  disabled = false,
  onClick,
  color = "default",
  size = "small",
  wrap = true,
  component,
  to,
  href,
  type,
  ...iconButtonProps
}: ActionIconButtonProps) {
  const button = (
    <IconButton
      size={size}
      color={color}
      disabled={disabled || loading}
      onClick={onClick}
      aria-label={title}
      {...(component ? { component, to, href } : { type: type ?? "button" })}
      {...iconButtonProps}
    >
      {loading ? <CircularProgress size={size === "large" ? 24 : 18} color="inherit" /> : ACTION_ICONS[variant]}
    </IconButton>
  );

  if (!wrap) {
    return (
      <Tooltip title={title}>
        {button}
      </Tooltip>
    );
  }

  return (
    <Tooltip title={title}>
      <span>{button}</span>
    </Tooltip>
  );
}

export type ActionIconLabelProps = {
  variant: ActionIconVariant;
  title: string;
  disabled?: boolean;
  children: ReactNode;
  color?: IconButtonProps["color"];
  size?: IconButtonProps["size"];
};

export function ActionIconLabel({
  variant,
  title,
  disabled = false,
  children,
  color = "default",
  size = "small",
}: ActionIconLabelProps) {
  return (
    <Tooltip title={title}>
      <span>
        <IconButton
          component="label"
          size={size}
          color={color}
          disabled={disabled}
          aria-label={title}
        >
          {ACTION_ICONS[variant]}
          {children}
        </IconButton>
      </span>
    </Tooltip>
  );
}
