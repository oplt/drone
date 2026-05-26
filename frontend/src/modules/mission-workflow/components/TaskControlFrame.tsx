import type { ReactNode } from "react";
import {
  Box,
  Collapse,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import ChevronLeftRoundedIcon from "@mui/icons-material/ChevronLeftRounded";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";

type TaskControlFrameProps = {
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  children: ReactNode;
  title?: string;
};

export function TaskControlFrame({
  expanded,
  onExpandedChange,
  children,
  title = "Preflight & Commands",
}: TaskControlFrameProps) {
  return (
    <Paper
      variant="outlined"
      sx={{
        borderRadius: 2,
        borderColor: "divider",
        overflow: "hidden",
        bgcolor: "background.paper",
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ px: expanded ? 1.5 : 1, py: 1 }}
      >
        {expanded && (
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              {title}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Mission readiness and live actions
            </Typography>
          </Box>
        )}
        <Tooltip title={expanded ? "Collapse controls to right" : "Expand controls"}>
          <IconButton
            size="small"
            aria-label={expanded ? "Collapse preflight and command panels" : "Expand preflight and command panels"}
            aria-expanded={expanded}
            onClick={() => onExpandedChange(!expanded)}
            sx={{ ml: "auto" }}
          >
            {expanded ? <ChevronRightRoundedIcon /> : <ChevronLeftRoundedIcon />}
          </IconButton>
        </Tooltip>
      </Stack>
      <Collapse in={expanded}>
        <Stack spacing={2} sx={{ px: 1, pb: 1 }}>
          {children}
        </Stack>
      </Collapse>
    </Paper>
  );
}
