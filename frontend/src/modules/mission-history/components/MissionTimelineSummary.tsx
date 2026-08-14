import { Box, CircularProgress, Divider, Paper, Stack, Typography } from "@mui/material";

import { formatMissionTimelineTs } from "../utils/missionTimelineFormat";
import { MissionSectionError } from "./MissionSectionError";

type MissionSummary = {
  mission_name?: string;
  mission_type?: string;
  state?: string;
  created_at?: number;
  updated_at?: number;
  preflight_run_id?: string;
  last_error?: string;
};

type MissionQuery = {
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  error: unknown;
  data?: MissionSummary;
  refetch: () => Promise<unknown>;
};

export function MissionTimelineSummary({ missionQ }: { missionQ: MissionQuery }) {
  const mission = missionQ.data;

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      {missionQ.isLoading ? (
        <CircularProgress size={24} />
      ) : missionQ.error ? (
        <MissionSectionError
          section="Mission summary"
          error={missionQ.error}
          retrying={missionQ.isFetching}
          onRetry={() => void missionQ.refetch()}
        />
      ) : mission ? (
        <Stack spacing={1}>
          <Typography fontWeight={600} noWrap>
            {mission.mission_name}
          </Typography>
          <Divider />
          <Box>
            <Typography variant="caption" color="text.secondary">
              Type
            </Typography>
            <Typography variant="body2">{mission.mission_type}</Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              State
            </Typography>
            <Typography variant="body2">{mission.state}</Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Created
            </Typography>
            <Typography variant="body2">{formatMissionTimelineTs(mission.created_at)}</Typography>
          </Box>
          {mission.updated_at && (
            <Box>
              <Typography variant="caption" color="text.secondary">
                Last updated
              </Typography>
              <Typography variant="body2">{formatMissionTimelineTs(mission.updated_at)}</Typography>
            </Box>
          )}
          {mission.preflight_run_id && (
            <Box>
              <Typography variant="caption" color="text.secondary">
                Preflight ID
              </Typography>
              <Typography variant="body2" sx={{ wordBreak: "break-all", fontSize: 11 }}>
                {mission.preflight_run_id}
              </Typography>
            </Box>
          )}
          {mission.last_error && (
            <Box>
              <Typography variant="caption" color="error">
                Error
              </Typography>
              <Typography variant="body2" color="error">
                {mission.last_error}
              </Typography>
            </Box>
          )}
        </Stack>
      ) : null}
    </Paper>
  );
}
