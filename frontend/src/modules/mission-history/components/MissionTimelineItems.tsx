import { useId, useState } from "react";
import { Box, Chip, Collapse, Divider, IconButton, Stack, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import FlightIcon from "@mui/icons-material/Flight";
import PauseCircleIcon from "@mui/icons-material/PauseCircle";
import StopCircleIcon from "@mui/icons-material/StopCircle";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import PersonIcon from "@mui/icons-material/Person";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";

import { formatMissionTimelineTs } from "../utils/missionTimelineFormat";

function stateIcon(state: string) {
  switch (state) {
    case "running":
    case "airborne":
      return <FlightIcon fontSize="small" color="primary" />;
    case "paused":
      return <PauseCircleIcon fontSize="small" color="warning" />;
    case "completed":
      return <CheckCircleIcon fontSize="small" color="success" />;
    case "aborted":
    case "failed":
      return <StopCircleIcon fontSize="small" color="error" />;
    default:
      return <FlightIcon fontSize="small" color="disabled" />;
  }
}

export function MissionTimelineTransitionItem({ item }: { item: Record<string, unknown> }) {
  return (
    <Stack direction="row" spacing={1.5} alignItems="flex-start">
      <Box sx={{ pt: 0.25 }}>{stateIcon(String(item.state ?? ""))}</Box>
      <Box>
        <Typography variant="body2" fontWeight={500}>
          {String(item.state ?? "")}
          {item.trigger && (
            <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
              via {String(item.trigger)}
            </Typography>
          )}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {formatMissionTimelineTs(item.entered_at as number | null | undefined)}
        </Typography>
        {item.reason && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            {String(item.reason)}
          </Typography>
        )}
      </Box>
    </Stack>
  );
}

export function MissionTimelineCommandItem({ item }: { item: Record<string, unknown> }) {
  return (
    <Stack direction="row" spacing={1.5} alignItems="flex-start">
      <Box sx={{ pt: 0.25 }}>
        <PersonIcon fontSize="small" color={item.accepted ? "primary" : "disabled"} />
      </Box>
      <Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="body2" fontWeight={500}>
            {String(item.command ?? "")}
          </Typography>
          <Chip
            label={item.accepted ? "accepted" : "rejected"}
            size="small"
            color={item.accepted ? "success" : "default"}
          />
        </Stack>
        <Typography variant="caption" color="text.secondary">
          {formatMissionTimelineTs(item.requested_at as number | null | undefined)} · {String(item.state_before ?? "")} →{" "}
          {String(item.state_after ?? "")}
        </Typography>
        {item.message && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            {String(item.message)}
          </Typography>
        )}
      </Box>
    </Stack>
  );
}

export function MissionTimelineEventItem({ item }: { item: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const contentId = useId();
  const data = item.data as Record<string, unknown> | undefined;
  const hasData = data && Object.keys(data).length > 0;

  return (
    <Stack direction="row" spacing={1.5} alignItems="flex-start">
      <Box sx={{ pt: 0.25 }}>
        <NotificationsActiveIcon fontSize="small" color="action" />
      </Box>
      <Box sx={{ flex: 1 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="body2" fontWeight={500}>
            {String(item.type ?? "")}
          </Typography>
          {hasData && (
            <IconButton
              size="small"
              aria-label={open ? "Collapse event data" : "Expand event data"}
              aria-expanded={open}
              aria-controls={contentId}
              onClick={() => setOpen((value) => !value)}
              sx={{ p: 0 }}
            >
              {open ? (
                <KeyboardArrowUpIcon fontSize="small" />
              ) : (
                <KeyboardArrowDownIcon fontSize="small" />
              )}
            </IconButton>
          )}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          {formatMissionTimelineTs(item.created_at as number | null | undefined)}
        </Typography>
        <Collapse id={contentId} in={open}>
          <Box
            component="pre"
            sx={{
              mt: 0.5,
              p: 1,
              bgcolor: "action.hover",
              borderRadius: 1,
              fontSize: 11,
              overflow: "auto",
              maxHeight: 200,
            }}
          >
            {JSON.stringify(data, null, 2)}
          </Box>
        </Collapse>
      </Box>
    </Stack>
  );
}

export function MissionTimelineEventsList({
  entries,
}: {
  entries: Array<{ kind: "transition" | "command" | "event"; data: Record<string, unknown> }>;
}) {
  return (
    <Stack spacing={0} divider={<Divider sx={{ my: 1 }} />}>
      {entries.map((entry, index) => {
        if (entry.kind === "transition") {
          return <MissionTimelineTransitionItem key={`t-${index}`} item={entry.data} />;
        }
        if (entry.kind === "command") {
          return <MissionTimelineCommandItem key={`c-${index}`} item={entry.data} />;
        }
        return <MissionTimelineEventItem key={`e-${index}`} item={entry.data} />;
      })}
    </Stack>
  );
}
