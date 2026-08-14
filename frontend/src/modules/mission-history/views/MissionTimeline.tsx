import { useNavigate, useParams } from "react-router-dom";
import { Box, Chip, CircularProgress, IconButton, Paper, Stack, Tooltip, Typography } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

import { MissionTimelineComplianceSection } from "../components/MissionTimelineComplianceSection";
import { MissionTimelineExportButton } from "../components/MissionTimelineExportButton";
import { MissionTimelineEventsList } from "../components/MissionTimelineItems";
import { MissionTimelinePreflightSection } from "../components/MissionTimelinePreflightSection";
import { MissionTimelineSummary } from "../components/MissionTimelineSummary";
import { MissionSectionError } from "../components/MissionSectionError";
import { useMissionTimelineData } from "../hooks/useMissionTimelineData";

export default function MissionTimeline() {
  const { flightId } = useParams<{ flightId: string }>();
  const navigate = useNavigate();
  const {
    missionQ,
    preflightQ,
    complianceQ,
    timelineQueries,
    mission,
    loading,
    entries,
    timelineHasErrors,
  } = useMissionTimelineData(flightId);

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1100, mx: "auto" }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <Tooltip title="Back to Operations">
          <IconButton
            aria-label="Back to Operations"
            onClick={() => navigate("/dashboard")}
            size="small"
          >
            <ArrowBackIcon />
          </IconButton>
        </Tooltip>
        <Typography variant="h6" fontWeight={600}>
          Mission Timeline
        </Typography>
        {mission && <Chip label={mission.state} size="small" />}
        <Box sx={{ flex: 1 }} />
        {flightId && <MissionTimelineExportButton flightId={flightId} />}
      </Stack>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "280px 1fr" },
          gap: 2,
          alignItems: "start",
        }}
      >
        <MissionTimelineSummary missionQ={missionQ} />

        <Stack spacing={2}>
          {preflightQ.error ? (
            <MissionSectionError
              section="Preflight"
              error={preflightQ.error}
              retrying={preflightQ.isFetching}
              onRetry={() => void preflightQ.refetch()}
            />
          ) : (
            preflightQ.data && <MissionTimelinePreflightSection data={preflightQ.data} />
          )}

          {complianceQ.error ? (
            <MissionSectionError
              section="Compliance"
              error={complianceQ.error}
              retrying={complianceQ.isFetching}
              onRetry={() => void complianceQ.refetch()}
            />
          ) : (
            complianceQ.data && <MissionTimelineComplianceSection data={complianceQ.data} />
          )}

          {timelineQueries.map(({ section, query }) =>
            query.error ? (
              <MissionSectionError
                key={section}
                section={section}
                error={query.error}
                retrying={query.isFetching}
                onRetry={() => void query.refetch()}
              />
            ) : null,
          )}

          {loading ? (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress />
            </Box>
          ) : entries.length === 0 && !timelineHasErrors ? (
            <Paper variant="outlined" sx={{ p: 3, textAlign: "center" }}>
              <Typography color="text.secondary">No timeline events recorded.</Typography>
            </Paper>
          ) : entries.length > 0 ? (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1.5 }}>
                Events ({entries.length})
              </Typography>
              <MissionTimelineEventsList entries={entries} />
            </Paper>
          ) : null}
        </Stack>
      </Box>
    </Box>
  );
}
