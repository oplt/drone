import { Alert, Box, Typography } from "@mui/material";

type Props = {
  missionName: string;
  missionState: string;
  activeFlightId?: string | null;
  lastError?: string | null;
};

export function WarehouseMissionStatusSummary({
  missionName,
  missionState,
  activeFlightId,
  lastError,
}: Props) {
  return (
    <>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
          gap: 1.5,
        }}
      >
        <Box>
          <Typography variant="caption" color="text.secondary">
            Mission
          </Typography>
          <Typography variant="body1">{missionName}</Typography>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">
            State
          </Typography>
          <Typography variant="body1" sx={{ textTransform: "capitalize" }}>
            {missionState.replace(/_/g, " ")}
          </Typography>
        </Box>
        {activeFlightId && (
          <Box sx={{ gridColumn: { sm: "1 / -1" } }}>
            <Typography variant="caption" color="text.secondary">
              Active Flight
            </Typography>
            <Typography variant="body1">{activeFlightId}</Typography>
          </Box>
        )}
      </Box>
      {lastError && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {lastError}
        </Alert>
      )}
    </>
  );
}
