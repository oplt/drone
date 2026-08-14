import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  Box,
  Drawer,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import type { SxProps, Theme } from "@mui/material/styles";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import FlightTakeoffRoundedIcon from "@mui/icons-material/FlightTakeoffRounded";

const EDGE_TAB_SLOT_HEIGHT = 76;
const EDGE_TAB_GAP = 6;

function edgeTabVerticalOffset(index: number, count: number): number {
  if (count <= 1) return 0;
  const clusterOffset = ((count - 1) * (EDGE_TAB_SLOT_HEIGHT + EDGE_TAB_GAP)) / 2;
  return index * (EDGE_TAB_SLOT_HEIGHT + EDGE_TAB_GAP) - clusterOffset;
}

export type TaskPreflightCommandsDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
  title?: string;
  subtitle?: string;
  /** Vertical label on the edge tab when the drawer is closed. */
  tabLabel?: string;
  /** Icon shown on the edge tab. Defaults to takeoff icon. */
  tabIcon?: ReactNode;
  /** Index when multiple edge tabs are stacked on the right (0 = upper). */
  edgeTabIndex?: number;
  /** Total number of edge tabs on this page. */
  edgeTabCount?: number;
  paperSx?: SxProps<Theme>;
};

export function TaskPreflightCommandsDrawer({
  open,
  onOpenChange,
  children,
  title = "Preflight & Commands",
  subtitle = "Mission readiness and live actions",
  tabLabel = "OPS",
  tabIcon,
  edgeTabIndex = 0,
  edgeTabCount = 1,
  paperSx,
}: TaskPreflightCommandsDrawerProps) {
  const theme = useTheme();
  const bottomSheet = useMediaQuery(theme.breakpoints.down("md"));
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const tabOffsetY = edgeTabVerticalOffset(edgeTabIndex, edgeTabCount);
  const drawerDuration = reduceMotion ? 0 : 200;

  const edgeTab =
    !open ? (
      <Tooltip title={title} placement={bottomSheet ? "top" : "left"}>
        <Box
          component="button"
          type="button"
          aria-label={`Open ${title}`}
          onClick={() => onOpenChange(true)}
          sx={{
            position: "fixed",
            zIndex: theme.zIndex.drawer + 2,
            display: "flex",
            alignItems: "center",
            gap: 0.5,
            border: "1px solid",
            bgcolor: "background.paper",
            color: "primary.main",
            cursor: "pointer",
            boxShadow: theme.shadows[4],
            transition: reduceMotion
              ? "none"
              : "background-color 160ms ease, box-shadow 160ms ease",
            "&:hover": {
              bgcolor: "action.hover",
              boxShadow: theme.shadows[8],
            },
            "&:focus-visible": {
              outline: `2px solid ${theme.palette.primary.main}`,
              outlineOffset: 2,
            },
            ...(bottomSheet
              ? {
                  left: `calc(50% + ${tabOffsetY * 0.15}px)`,
                  bottom: "calc(12px + env(safe-area-inset-bottom, 0px))",
                  top: "auto",
                  right: "auto",
                  transform: "translateX(-50%)",
                  flexDirection: "row",
                  py: 1,
                  px: 1.5,
                  borderRadius: 999,
                  borderRight: "1px solid",
                  borderColor: "divider",
                }
              : {
                  right: 0,
                  top: `calc(50% + ${tabOffsetY}px)`,
                  transform: "translateY(-50%)",
                  flexDirection: "column",
                  py: 1.25,
                  px: 0.75,
                  borderRight: "none",
                  borderColor: "divider",
                  borderTopLeftRadius: 12,
                  borderBottomLeftRadius: 12,
                }),
          }}
        >
          {tabIcon ?? <FlightTakeoffRoundedIcon fontSize="small" />}
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              letterSpacing: "0.06em",
              fontSize: "0.65rem",
              lineHeight: 1.2,
              ...(bottomSheet
                ? {}
                : {
                    writingMode: "vertical-rl",
                    transform: "rotate(180deg)",
                  }),
            }}
          >
            {tabLabel}
          </Typography>
        </Box>
      </Tooltip>
    ) : null;

  return (
    <>
      {typeof document !== "undefined"
        ? createPortal(edgeTab, document.body)
        : edgeTab}

      <Drawer
        anchor={bottomSheet ? "bottom" : "right"}
        open={open}
        onClose={() => onOpenChange(false)}
        transitionDuration={drawerDuration}
        slotProps={{
          backdrop: {
            sx: {
              bgcolor: "rgba(8, 12, 18, 0.42)",
              transitionDuration: `${drawerDuration}ms`,
            },
          },
        }}
        PaperProps={{
          sx: [
            {
              transitionDuration: `${drawerDuration}ms`,
            },
            bottomSheet
              ? {
                  width: "100%",
                  maxHeight: "min(78vh, 720px)",
                  borderTopLeftRadius: 16,
                  borderTopRightRadius: 16,
                  borderTop: "1px solid",
                  borderColor: "divider",
                  bgcolor: "background.paper",
                  pb: "env(safe-area-inset-bottom, 0px)",
                  backgroundImage: (t: Theme) =>
                    `linear-gradient(180deg, ${t.palette.primary.main}14 0%, transparent 28%)`,
                }
              : {
                  width: { xs: "min(100vw, 420px)", sm: 440, md: 460 },
                  borderLeft: "1px solid",
                  borderColor: "divider",
                  bgcolor: "background.paper",
                  backgroundImage: (t: Theme) =>
                    `linear-gradient(180deg, ${t.palette.primary.main}14 0%, transparent 28%)`,
                },
            ...(paperSx ? (Array.isArray(paperSx) ? paperSx : [paperSx]) : []),
          ],
        }}
      >
        <Stack sx={{ height: "100%", minHeight: 0 }}>
          <Stack
            direction="row"
            alignItems="flex-start"
            justifyContent="space-between"
            spacing={1}
            sx={{
              px: 2,
              py: 1.5,
              borderBottom: "1px solid",
              borderColor: "divider",
              flexShrink: 0,
            }}
          >
            <Box sx={{ minWidth: 0, pr: 1 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                {title}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {subtitle}
              </Typography>
            </Box>
            <Tooltip title="Close">
              <IconButton
                size="small"
                aria-label={`Close ${title}`}
                onClick={() => onOpenChange(false)}
                sx={{ mt: -0.25 }}
              >
                <CloseRoundedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>

          <Box
            sx={{
              flex: 1,
              minHeight: 0,
              overflow: "auto",
              px: 1.5,
              py: 1.5,
            }}
          >
            <Stack spacing={1.5}>{children}</Stack>
          </Box>
        </Stack>
      </Drawer>
    </>
  );
}
