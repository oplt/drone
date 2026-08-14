import type { ReactNode } from "react";
import { useState } from "react";
import { Button, Collapse, Paper, Stack, Typography, useMediaQuery, useTheme } from "@mui/material";
import { radius } from "../../../shared/theme/themePrimitives";

export function MapEngineSelectionOverlay({
  children,
  followEnabled,
  onFollowEnabledChange,
  defaultExpanded = false,
}: {
  children: ReactNode;
  followEnabled?: boolean;
  onFollowEnabledChange?: (next: boolean) => void;
  defaultExpanded?: boolean;
}) {
  const theme = useTheme();
  const narrow = useMediaQuery(theme.breakpoints.down("md"));
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <Paper
      variant="mapOverlay"
      elevation={0}
      sx={{
        position: "absolute",
        left: 10,
        // Keep clear of bottom draw-tool sheet on tablet/phone.
        ...(narrow
          ? { top: 10, bottom: "auto" }
          : { bottom: 10, top: "auto" }),
        zIndex: 1300,
        pointerEvents: "auto",
        p: 1,
        borderRadius: radius.sm,
        maxWidth: "calc(100% - 20px)",
      }}
    >
      <Stack spacing={0.75}>
        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
          <Button size="small" variant="text" onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Hide map tools" : "Map tools"}
          </Button>
          {onFollowEnabledChange ? (
            <Button
              size="small"
              variant={followEnabled ? "contained" : "outlined"}
              onClick={() => onFollowEnabledChange(!followEnabled)}
              aria-pressed={followEnabled}
            >
              {followEnabled ? "Follow on" : "Follow off"}
            </Button>
          ) : null}
        </Stack>
        <Collapse in={expanded} unmountOnExit>
          <Stack spacing={0.75}>
            <Typography variant="caption" color="text.secondary">
              Engine and camera modes
            </Typography>
            {children}
          </Stack>
        </Collapse>
      </Stack>
    </Paper>
  );
}
