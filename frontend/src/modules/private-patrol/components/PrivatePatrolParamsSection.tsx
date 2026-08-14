import { useCallback } from "react";
import { Box, Paper, Tab, Tabs, Typography } from "@mui/material";
import type { usePrivatePatrolMission } from "../hooks/usePrivatePatrolMission";
import type { PatrolSensorIntegration } from "../api/eventTriggerConfigApi";
import { PatrolAiTasksSection } from "./params/PatrolAiTasksSection";
import { PatrolEventTriggeredParamsFields } from "./params/PatrolEventTriggeredParamsFields";
import { PatrolGridSurveillanceParamsFields } from "./params/PatrolGridSurveillanceParamsFields";
import { PatrolPerimeterParamsFields } from "./params/PatrolPerimeterParamsFields";
import { PatrolPreviewStatusSection } from "./params/PatrolPreviewStatusSection";
import { PatrolWaypointParamsFields } from "./params/PatrolWaypointParamsFields";
import { PARAM_GRID_SX, PARAM_TABS, type ParamsTab } from "./params/patrolParamsLayout";

type MissionVm = ReturnType<typeof usePrivatePatrolMission>;

export function PrivatePatrolParamsSection({
  mission,
  selectedFieldId,
  hasPropertyGeofence,
  eventTriggerIntegration,
  eventTriggerSaving,
  eventTriggerSaveError,
}: {
  mission: MissionVm;
  selectedFieldId: number | null;
  hasPropertyGeofence: boolean;
  eventTriggerIntegration: PatrolSensorIntegration | null;
  eventTriggerSaving?: boolean;
  eventTriggerSaveError?: string | null;
}) {
  const {
    gridParams,
    setGridParams,
    isWaypointPatrol,
    isGridSurveillance,
    isEventTriggeredPatrol,
    hasEventTriggerGeometry,
    hasRequiredTaskGeometry,
    eventLocation,
    alt,
    gridPreview,
    patrolPreviewStats,
    gridPreviewTooDense,
    gridPreviewError,
    previewLoading,
    scheduledStartAt,
    repeatStartAt,
    repeatWaitingForCompletion,
    cancelScheduledStart,
  } = mission;

  const activeTab: ParamsTab = gridParams.event_triggered_enabled
    ? "event_triggered"
    : gridParams.task_type;

  const handleTabChange = useCallback(
    (_: React.SyntheticEvent, value: ParamsTab) => {
      if (value === "event_triggered") {
        setGridParams((p) => ({ ...p, event_triggered_enabled: true }));
        return;
      }
      setGridParams((p) => ({
        ...p,
        task_type: value,
        event_triggered_enabled: false,
      }));
    },
    [setGridParams],
  );

  const fieldProps = { gridParams, setGridParams, activeTab };

  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography variant="subtitle2" sx={{ mb: 0.75, fontWeight: 700 }}>
        Parameters
      </Typography>
      <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
        <Tabs
          value={activeTab}
          onChange={handleTabChange}
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            mb: 1,
            minHeight: 36,
            borderBottom: 1,
            borderColor: "divider",
            "& .MuiTab-root": {
              minHeight: 36,
              py: 0.5,
              px: 1.25,
            },
          }}
        >
          {PARAM_TABS.map((tab) => (
            <Tab key={tab.value} label={tab.label} value={tab.value} />
          ))}
        </Tabs>

        <Box sx={PARAM_GRID_SX}>
          {activeTab === "perimeter_patrol" && (
            <PatrolPerimeterParamsFields {...fieldProps} />
          )}
          {activeTab === "waypoint_patrol" && (
            <PatrolWaypointParamsFields {...fieldProps} />
          )}
          {activeTab === "grid_surveillance" && (
            <PatrolGridSurveillanceParamsFields {...fieldProps} />
          )}
          {activeTab === "event_triggered" && (
            <PatrolEventTriggeredParamsFields
              {...fieldProps}
              hasEventTriggerGeometry={hasEventTriggerGeometry}
              eventTriggerIntegration={eventTriggerIntegration}
              selectedFieldId={selectedFieldId}
              hasPropertyGeofence={hasPropertyGeofence}
              eventTriggerSaving={eventTriggerSaving}
              eventTriggerSaveError={eventTriggerSaveError}
              eventLocation={eventLocation}
            />
          )}

          <PatrolAiTasksSection gridParams={gridParams} setGridParams={setGridParams} />

          <PatrolPreviewStatusSection
            gridParams={gridParams}
            isGridSurveillance={isGridSurveillance}
            isWaypointPatrol={isWaypointPatrol}
            isEventTriggeredPatrol={isEventTriggeredPatrol}
            hasEventTriggerGeometry={hasEventTriggerGeometry}
            hasRequiredTaskGeometry={hasRequiredTaskGeometry}
            alt={alt}
            gridPreview={gridPreview}
            patrolPreviewStats={patrolPreviewStats}
            gridPreviewTooDense={gridPreviewTooDense}
            gridPreviewError={gridPreviewError}
            previewLoading={previewLoading}
            scheduledStartAt={scheduledStartAt}
            repeatStartAt={repeatStartAt}
            repeatWaitingForCompletion={repeatWaitingForCompletion}
            cancelScheduledStart={cancelScheduledStart}
          />
        </Box>
      </Paper>
    </Box>
  );
}
