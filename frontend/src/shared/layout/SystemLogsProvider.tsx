import {
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useAppLogs, type AppLogEvent, type AppLogLevel } from "../logging";
import { SystemLogsContext } from "./systemLogsContext";

const logSeverityColor = (level: AppLogLevel): "error" | "warning" | "info" | "default" => {
  if (level === "critical" || level === "error") return "error";
  if (level === "warn") return "warning";
  if (level === "info") return "info";
  return "default";
};

function formatTimestamp(value: string) {
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function SystemLogCard({ item }: { item: AppLogEvent }) {
  const requestId = item.requestId ?? item.request_id;
  const flightId = item.flightId ?? item.flight_id;
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        borderRadius: 2,
        borderColor: item.level === "critical" ? "error.main" : "divider",
      }}
    >
      <Stack spacing={1}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
          <Typography variant="subtitle2">{item.message}</Typography>
          <Chip size="small" color={logSeverityColor(item.level)} label={item.level.toUpperCase()} />
        </Stack>
        <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap", rowGap: 0.75 }}>
          <Chip size="small" variant="outlined" label={item.source} />
          {requestId ? <Chip size="small" variant="outlined" label={`request ${requestId}`} /> : null}
          {flightId ? <Chip size="small" variant="outlined" label={`flight ${flightId}`} /> : null}
        </Stack>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          {formatTimestamp(item.timestamp)}
        </Typography>
        {item.details && Object.keys(item.details).length > 0 ? (
          <Box
            component="pre"
            sx={{
              m: 0,
              p: 1,
              borderRadius: 1,
              bgcolor: "action.hover",
              color: "text.secondary",
              fontSize: 12,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              maxHeight: 160,
              overflow: "auto",
            }}
          >
            {JSON.stringify(item.details, null, 2)}
          </Box>
        ) : null}
      </Stack>
    </Paper>
  );
}

export function SystemLogsProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [levelFilter, setLevelFilter] = useState<AppLogLevel | "all">("all");
  const appLogs = useAppLogs();
  const criticalCount = appLogs.filter((item) => item.level === "critical").length;
  const visibleLogs = useMemo(
    () => appLogs.filter((item) => levelFilter === "all" || item.level === levelFilter),
    [appLogs, levelFilter],
  );

  const setOpenStable = useCallback((next: boolean | ((prev: boolean) => boolean)) => {
    setOpen(next);
  }, []);

  const value = useMemo(
    () => ({ open, setOpen: setOpenStable, criticalCount }),
    [open, setOpenStable, criticalCount],
  );

  return (
    <SystemLogsContext.Provider value={value}>
      {children}
      <Drawer anchor="right" open={open} onClose={() => setOpen(false)}>
        <Box sx={{ width: { xs: 360, sm: 520 }, p: 2.5 }} role="dialog" aria-label="System events">
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
            <Stack spacing={0.5}>
              <Typography variant="h5" component="h2">
                System Events
              </Typography>
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                {appLogs.length} recent events
              </Typography>
            </Stack>
            <Chip
              size="small"
              color={criticalCount > 0 ? "error" : "default"}
              label={`${criticalCount} critical`}
            />
          </Stack>
          <Divider sx={{ mb: 2 }} />
          <Stack direction="row" spacing={0.75} sx={{ mb: 2, flexWrap: "wrap", rowGap: 0.75 }}>
            {(["all", "critical", "error", "warn", "info"] as const).map((level) => (
              <Chip
                key={level}
                clickable
                size="small"
                color={
                  levelFilter === level
                    ? level === "critical" || level === "error"
                      ? "error"
                      : "primary"
                    : "default"
                }
                variant={levelFilter === level ? "filled" : "outlined"}
                label={level.toUpperCase()}
                onClick={() => setLevelFilter(level)}
              />
            ))}
          </Stack>
          {visibleLogs.length === 0 ? (
            <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 2 }}>
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                No events match the selected severity.
              </Typography>
            </Paper>
          ) : (
            <Stack spacing={1.25}>
              {visibleLogs.map((item) => (
                <SystemLogCard key={item.id} item={item} />
              ))}
            </Stack>
          )}
        </Box>
      </Drawer>
    </SystemLogsContext.Provider>
  );
}
