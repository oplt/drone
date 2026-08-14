import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Chip,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import type { SxProps, Theme } from "@mui/material/styles";
import { useState } from "react";
import { useMissionCommands } from "../hooks/useMissionCommands";
import type { MissionLifecycleSlice, MissionLifecycleState, MissionStatusPayload } from "../types";
import { stateChipColor } from "./command/formatters";
import { CommandAuditSection } from "./command/CommandAuditSection";
import { CommandControlsSection } from "./command/CommandControlsSection";
import { CommandMetricsSection } from "./command/CommandMetricsSection";
import { MissionTimelineSection } from "./command/MissionTimelineSection";
import { OpsHealthSection } from "./command/OpsHealthSection";

export function MissionCommandPanel({
  telemetry,
  droneConnected,
  missionStatus = null,
  activeFlightId = null,
  title = "Command Panel",
  defaultExpanded = true,
  sx,
  apiBase,
  getTokenFn,
}: {
  telemetry: unknown;
  droneConnected: boolean;
  missionStatus?: MissionStatusPayload | null;
  activeFlightId?: string | null;
  /** @deprecated Transport uses shared HTTP client; kept for compatibility. */
  apiBase?: string;
  /** @deprecated Session token resolved in mission-runtime hooks. */
  getTokenFn?: () => string | null;
  title?: string;
  defaultExpanded?: boolean;
  sx?: SxProps<Theme>;
}) {
  void apiBase;
  void getTokenFn;
  const [secondaryTab, setSecondaryTab] = useState<"audit" | "ops">("audit");

  const lifecycle =
    missionStatus?.mission_lifecycle ??
    (missionStatus?.flight_id || missionStatus?.mission_name
      ? {
          flight_id: missionStatus?.flight_id ?? null,
          mission_name: missionStatus?.mission_name,
        }
      : null);
  const lifecycleState = lifecycle?.state ?? null;
  const flightId = lifecycle?.flight_id ?? activeFlightId ?? null;

  const {
    issueCommand,
    busyCommand,
    message,
    error,
    capabilities,
    recentAudit,
    recentTimeline,
    opsHealth,
    auditLoading,
    auditError,
    timelineError,
    opsError,
  } = useMissionCommands({ flightId, missionStatus });

  const lifecycleForControls: MissionLifecycleSlice | null =
    missionStatus?.mission_lifecycle ??
    (lifecycle && "state" in lifecycle
      ? lifecycle
      : lifecycle
        ? { ...lifecycle, state: lifecycleState ?? undefined }
        : null);

  return (
    <Accordion
      disableGutters
      defaultExpanded={defaultExpanded}
      sx={[
        {
          borderRadius: 2,
          border: "1px solid",
          borderColor: "divider",
          "&:before": { display: "none" },
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreRoundedIcon />}
        sx={{ px: 2, py: 0.25, minHeight: 0 }}
      >
        <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
          <Typography variant="subtitle1">{title}</Typography>
          {lifecycleState && (
            <Chip
              size="small"
              label={lifecycleState.toUpperCase()}
              color={stateChipColor(lifecycleState as MissionLifecycleState)}
            />
          )}
        </Stack>
      </AccordionSummary>

      <AccordionDetails sx={{ px: 1, pb: 1, pt: 0.5 }}>
        <Stack spacing={1}>
          {/* Primary: telemetry strip + critical controls stay above fold */}
          <CommandMetricsSection telemetry={telemetry} droneConnected={droneConnected} />
          <CommandControlsSection
            flightId={flightId}
            lifecycle={lifecycleForControls}
            capabilities={capabilities}
            busyCommand={busyCommand}
            message={message}
            error={error}
            onIssueCommand={(command) => {
              void issueCommand(command);
            }}
          />

          {/* Secondary: audit / ops health behind tabs */}
          <Tabs
            value={secondaryTab}
            onChange={(_, next: "audit" | "ops") => setSecondaryTab(next)}
            variant="fullWidth"
            sx={{ minHeight: 36, borderBottom: 1, borderColor: "divider" }}
          >
            <Tab label="Audit" value="audit" sx={{ minHeight: 36, py: 0.5 }} />
            <Tab label="Ops health" value="ops" sx={{ minHeight: 36, py: 0.5 }} />
          </Tabs>
          {secondaryTab === "audit" ? (
            <Stack spacing={0.5}>
              <CommandAuditSection
                recentAudit={recentAudit}
                auditLoading={auditLoading}
                auditError={auditError}
              />
              <MissionTimelineSection
                recentTimeline={recentTimeline}
                timelineError={timelineError}
              />
            </Stack>
          ) : (
            <OpsHealthSection opsHealth={opsHealth} opsError={opsError} />
          )}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
