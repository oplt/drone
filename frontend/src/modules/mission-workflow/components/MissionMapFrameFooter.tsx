import type { ReactNode } from "react";
import { useState } from "react";
import {
  Box,
  Collapse,
  Divider,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import ExpandLessRoundedIcon from "@mui/icons-material/ExpandLessRounded";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";

type MissionMapFrameFooterProps = {
  mapSelection: ReactNode;
  setupTitle?: string;
  setupSubtitle?: string;
  setupContent: ReactNode;
  setupExpanded?: boolean;
  onSetupExpandedChange?: (expanded: boolean) => void;
};

export function MissionMapFrameFooter({
  mapSelection,
  setupTitle = "Set up",
  setupSubtitle,
  setupContent,
  setupExpanded,
  onSetupExpandedChange,
}: MissionMapFrameFooterProps) {
  const [internalExpanded, setInternalExpanded] = useState(false);
  const expanded = setupExpanded ?? internalExpanded;
  const setExpanded = onSetupExpandedChange ?? setInternalExpanded;

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.5,
        borderRadius: 2,
        flexShrink: 0,
      }}
    >
      <Stack
        direction={{ xs: "column", lg: "row" }}
        spacing={2}
        divider={<Divider flexItem orientation="vertical" sx={{ display: { xs: "none", lg: "block" } }} />}
      >
        <Box sx={{ flex: "1 1 240px", minWidth: 0 }}>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 1, fontWeight: 600, letterSpacing: "0.04em" }}
          >
            Maps
          </Typography>
          {mapSelection}
        </Box>

        <Box sx={{ flex: "1.2 1 320px", minWidth: 0 }}>
          <Stack
            direction="row"
            alignItems="flex-start"
            justifyContent="space-between"
            spacing={1}
          >
            <Stack direction="row" spacing={1} alignItems="flex-start" sx={{ minWidth: 0 }}>
              <TuneRoundedIcon fontSize="small" color="primary" sx={{ mt: 0.25 }} />
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
                  {setupTitle}
                </Typography>
                {setupSubtitle ? (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                    {setupSubtitle}
                  </Typography>
                ) : null}
              </Box>
            </Stack>
            <Tooltip title={expanded ? "Collapse setup" : "Expand setup"}>
              <IconButton
                size="small"
                aria-label={expanded ? "Collapse setup section" : "Expand setup section"}
                aria-expanded={expanded}
                onClick={() => setExpanded(!expanded)}
                sx={{ mt: -0.25, flexShrink: 0 }}
              >
                {expanded ? <ExpandLessRoundedIcon /> : <ExpandMoreRoundedIcon />}
              </IconButton>
            </Tooltip>
          </Stack>

          <Collapse in={expanded}>
            <Stack spacing={1.5} sx={{ pt: 1.5 }}>
              {setupContent}
            </Stack>
          </Collapse>
        </Box>
      </Stack>
    </Paper>
  );
}
