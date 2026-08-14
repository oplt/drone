import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { PageSection } from "../../../shared/layout/PageLayout";
import {
  sortDashboardAlerts,
  toMuiSeverity,
  type DashboardAlertItem,
} from "../utils/dashboardAlerts";

type DashboardAlertsPanelProps = {
  items: DashboardAlertItem[];
  /** When set, distinguishes load failure from a quiet (empty) alert board. */
  loadError?: string | null;
  onRetryLoad?: () => void;
};

export default function DashboardAlertsPanel({
  items,
  loadError = null,
  onRetryLoad,
}: DashboardAlertsPanelProps) {
  const ranked = sortDashboardAlerts(items);
  const visibleItems = ranked.slice(0, 3);
  const hiddenCount = Math.max(0, ranked.length - visibleItems.length);

  return (
    <PageSection
      title="Alerts"
      description="Ranked by severity, then recency. Click an item to open Alert Center."
      sx={{ height: "100%", p: 2 }}
    >
      {loadError ? (
        <Stack spacing={1}>
          <Alert severity="error">
            Failed to load alerts. {loadError}
          </Alert>
          {onRetryLoad ? (
            <Button size="small" variant="outlined" onClick={onRetryLoad}>
              Retry alerts
            </Button>
          ) : null}
        </Stack>
      ) : ranked.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No open alerts — telemetry and safety thresholds are quiet.
        </Typography>
      ) : (
        <Stack spacing={1}>
          {visibleItems.map((item) => (
            <Tooltip
              key={item.id}
              title={`${item.title}: ${item.message}`}
              arrow
            >
              <Alert
                severity={toMuiSeverity(item.severity)}
                onClick={item.onOpen}
                sx={{
                  py: 0.5,
                  cursor: item.onOpen ? "pointer" : "default",
                  "& .MuiAlert-message": {
                    width: "100%",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  },
                }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip
                    size="small"
                    label={String(item.severity).toUpperCase()}
                    color={toMuiSeverity(item.severity) === "error" ? "error" : "default"}
                    sx={{ height: 20 }}
                  />
                  <Typography component="span" variant="body2" noWrap>
                    {item.title}
                  </Typography>
                </Stack>
              </Alert>
            </Tooltip>
          ))}
          {hiddenCount > 0 ? (
            <Tooltip
              title={ranked
                .slice(3)
                .map((item) => `${item.title}: ${item.message}`)
                .join("\n")}
              arrow
            >
              <Chip
                size="small"
                label={`+${hiddenCount} more`}
                onClick={ranked[0]?.onOpen}
                clickable={Boolean(ranked[0]?.onOpen)}
              />
            </Tooltip>
          ) : null}
        </Stack>
      )}
    </PageSection>
  );
}
