import { useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import { ActionIconButton } from "../../shared/ui/ActionIconButton";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import BugReportRoundedIcon from "@mui/icons-material/BugReportRounded";
import NotificationsRoundedIcon from "@mui/icons-material/NotificationsRounded";
import ColorModeIconDropdown from "../../shared/theme/ColorModeIconDropdown";
import ConsoleToolbar from "../../shared/layout/ConsoleToolbar";
import MenuButton from "../../shared/layout/MenuButton";
import ConsoleSearch from "../../shared/layout/Search";
import { useAlertCenter, type AlertItem } from "../../modules/alerts";
import { useAppLogs, type AppLogEvent, type AppLogLevel } from "../../shared/logging";
import CustomDatePicker from "./CustomDatePicker";

const severityColor = (severity: string): "error" | "warning" | "info" | "default" => {
  const normalized = String(severity || "").toLowerCase();
  if (normalized === "critical" || normalized === "high") return "error";
  if (normalized === "medium") return "warning";
  if (normalized === "low") return "info";
  return "default";
};

const formatTimestamp = (value: string) => {
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

function AlertCard({
  item,
  onAcknowledge,
  onResolve,
  pending,
}: {
  item: AlertItem;
  pending: boolean;
  onAcknowledge: () => Promise<void>;
  onResolve: () => Promise<void>;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
      <Stack spacing={1.25}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
          <Typography variant="subtitle2">{item.title}</Typography>
          <Chip size="small" color={severityColor(item.severity)} label={item.severity.toUpperCase()} />
        </Stack>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          {item.message}
        </Typography>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          Triggered {formatTimestamp(item.last_triggered_at)}
        </Typography>
        <Stack direction="row" spacing={0.25}>
          <ActionIconButton
            variant="check"
            title="Acknowledge"
            disabled={pending || item.status !== "open"}
            onClick={() => void onAcknowledge()}
          />
          <ActionIconButton
            variant="check"
            title="Resolve"
            color="success"
            disabled={pending}
            onClick={() => void onResolve()}
          />
        </Stack>
      </Stack>
    </Paper>
  );
}

const logSeverityColor = (level: AppLogLevel): "error" | "warning" | "info" | "default" => {
  if (level === "critical" || level === "error") return "error";
  if (level === "warn") return "warning";
  if (level === "info") return "info";
  return "default";
};

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

export default function Header() {
  const { alerts, openCount, loading, drawerOpen, setDrawerOpen, refresh, acknowledgeAlert, resolveAlert } =
    useAlertCenter();
  const appLogs = useAppLogs();
  const [pendingAlertId, setPendingAlertId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [logsDrawerOpen, setLogsDrawerOpen] = useState(false);
  const [levelFilter, setLevelFilter] = useState<AppLogLevel | "all">("all");

  const criticalLogCount = appLogs.filter((item) => item.level === "critical").length;
  const visibleLogs = useMemo(
    () => appLogs.filter((item) => levelFilter === "all" || item.level === levelFilter),
    [appLogs, levelFilter],
  );

  const handleAcknowledge = async (alertId: number) => {
    setPendingAlertId(alertId);
    setActionError(null);
    try {
      await acknowledgeAlert(alertId);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to acknowledge alert");
    } finally {
      setPendingAlertId(null);
    }
  };

  const handleResolve = async (alertId: number) => {
    setPendingAlertId(alertId);
    setActionError(null);
    try {
      await resolveAlert(alertId);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to resolve alert");
    } finally {
      setPendingAlertId(null);
    }
  };

  return (
    <>
      <ConsoleToolbar
        leading={<ConsoleSearch />}
        trailing={
          <>
            <CustomDatePicker />
            <Chip size="small" color="success" label="Telemetry live" />
            <MenuButton
              showBadge={openCount > 0}
              aria-label="Open notifications"
              onClick={() => setDrawerOpen(true)}
            >
              <NotificationsRoundedIcon />
            </MenuButton>
            <MenuButton
              showBadge={criticalLogCount > 0}
              aria-label="Open system events"
              onClick={() => setLogsDrawerOpen(true)}
            >
              <BugReportRoundedIcon />
            </MenuButton>
            <ColorModeIconDropdown />
          </>
        }
      />
      <Drawer anchor="right" open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        <Box sx={{ width: { xs: 340, sm: 440 }, p: 2.5 }} role="dialog" aria-label="Operational alerts">
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
            <Stack spacing={0.5}>
              <Typography variant="h5" component="h2">
                Operational Alerts
              </Typography>
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                {openCount} open alerts
              </Typography>
            </Stack>
            <ActionIconButton variant="refresh" title="Refresh" onClick={() => void refresh()} />
          </Stack>
          <Divider sx={{ mb: 2 }} />
          {actionError ? (
            <Alert severity="error" sx={{ mb: 1.5 }}>
              {actionError}
            </Alert>
          ) : null}
          {loading ? (
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
              <CircularProgress size={16} aria-hidden="true" />
              <Typography variant="body2">Updating alerts...</Typography>
            </Stack>
          ) : null}
          {alerts.length === 0 ? (
            <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                No active alerts. Telemetry, route safety, and system health are all within the
                configured thresholds.
              </Typography>
            </Paper>
          ) : (
            <Stack spacing={1.25}>
              {alerts.map((item) => (
                <AlertCard
                  key={item.id}
                  item={item}
                  pending={pendingAlertId === item.id}
                  onAcknowledge={() => handleAcknowledge(item.id)}
                  onResolve={() => handleResolve(item.id)}
                />
              ))}
            </Stack>
          )}
        </Box>
      </Drawer>
      <Drawer anchor="right" open={logsDrawerOpen} onClose={() => setLogsDrawerOpen(false)}>
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
              color={criticalLogCount > 0 ? "error" : "default"}
              label={`${criticalLogCount} critical`}
            />
          </Stack>
          <Divider sx={{ mb: 2 }} />
          <Stack direction="row" spacing={0.75} sx={{ mb: 2, flexWrap: "wrap", rowGap: 0.75 }}>
            {(["all", "critical", "error", "warn", "info"] as const).map((level) => (
              <Chip
                key={level}
                clickable
                size="small"
                color={levelFilter === level ? (level === "critical" || level === "error" ? "error" : "primary") : "default"}
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
    </>
  );
}
