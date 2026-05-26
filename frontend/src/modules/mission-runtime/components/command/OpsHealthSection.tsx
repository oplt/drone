import { Alert, Chip, Divider, Stack, Typography } from "@mui/material";
import { useMemo } from "react";
import type { OpsHealthResponse } from "../../types";
import { opsChipColor } from "./formatters";
import { StatRow } from "./StatRow";

export function OpsHealthSection({
  opsHealth,
  opsError,
}: {
  opsHealth: OpsHealthResponse | null;
  opsError: string | null;
}) {
  const queueRows = useMemo(() => {
    if (!opsHealth) return [];
    return [
      ["Flight events", opsHealth.queues.db_event],
      ["Lifecycle", opsHealth.queues.db_lifecycle],
      ["Raw ingest", opsHealth.queues.raw_event],
    ] as const;
  }, [opsHealth]);

  return (
    <Stack spacing={1} sx={{ pt: 0.5 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.6 }}>
        <Typography variant="caption" sx={{ letterSpacing: 0.6, fontWeight: 700 }}>
          OPS HEALTH
        </Typography>
        <Chip
          size="small"
          label={opsHealth?.status?.toUpperCase() ?? "UNKNOWN"}
          color={opsChipColor(opsHealth?.status)}
          variant={opsHealth ? "filled" : "outlined"}
        />
      </Stack>
      {opsError && <Alert severity="warning">{opsError}</Alert>}
      {!opsHealth ? (
        <Typography variant="caption" color="text.secondary">
          Operational health is unavailable right now.
        </Typography>
      ) : (
        <>
          <StatRow
            label="Telemetry Feed"
            value={
              opsHealth.telemetry.source_connected
                ? "Connected"
                : opsHealth.telemetry.running
                  ? "Waiting for source"
                  : "Stopped"
            }
          />
          <StatRow
            label="Last Update Age"
            value={
              opsHealth.telemetry.last_update_age_sec == null
                ? "--"
                : `${opsHealth.telemetry.last_update_age_sec.toFixed(1)}s`
            }
            valueSx={{
              color: opsHealth.telemetry.has_recent_update ? "success.main" : "warning.main",
            }}
          />
          <StatRow
            label="Video Link"
            value={
              !opsHealth.video.available
                ? "Unavailable"
                : opsHealth.video.healthy
                  ? `Healthy @ ${Math.round(opsHealth.video.fps ?? 0)} fps`
                  : "Degraded"
            }
            valueSx={{
              color:
                !opsHealth.video.available || opsHealth.video.healthy
                  ? "text.primary"
                  : "warning.main",
            }}
          />
          <StatRow
            label="Shadow Mode"
            value={
              opsHealth.shadow.shadow_mode_active
                ? `${opsHealth.shadow.old_path.error_rate_pct}% legacy write errors`
                : "Disabled"
            }
          />

          <Divider sx={{ my: 0.25 }} />

          <Typography variant="caption" color="text.secondary">
            Queue utilization
          </Typography>
          <Stack spacing={0.7}>
            {queueRows.map(([label, queue]) => (
              <Stack key={label} direction="row" justifyContent="space-between" spacing={1}>
                <Typography variant="caption" color="text.secondary">
                  {label}
                </Typography>
                <Typography
                  variant="caption"
                  sx={{
                    fontFamily: "monospace",
                    color: queue.utilization_pct >= 80 ? "warning.main" : "text.primary",
                  }}
                >
                  {queue.depth}/{queue.capacity} ({queue.utilization_pct.toFixed(0)}%)
                </Typography>
              </Stack>
            ))}
          </Stack>

          {opsHealth.active_mission && (
            <Alert severity="info" sx={{ py: 0.4 }}>
              Active mission: {opsHealth.active_mission.mission_name} (
              {opsHealth.active_mission.state})
            </Alert>
          )}

          {opsHealth.alerts.length > 0 ? (
            <Stack spacing={0.5}>
              {opsHealth.alerts.slice(0, 3).map((alert) => (
                <Alert key={alert} severity="warning" sx={{ py: 0.25 }}>
                  {alert}
                </Alert>
              ))}
            </Stack>
          ) : (
            <Typography variant="caption" color="text.secondary">
              No active operational warnings.
            </Typography>
          )}
        </>
      )}
    </Stack>
  );
}
