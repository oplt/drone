import {
  Alert,
  Button,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { Link as RouterLink, useParams } from "react-router-dom";
import { AgricultureLiveStatusPanel } from "../components/AgricultureLiveStatusPanel";
import { AgricultureAccessibilityBoundary } from "../components/AgricultureAccessibilityBoundary";
import { useAgricultureFlight } from "../hooks";

export default function AgricultureFlightPage() {
  const flightId = useParams<{ flightId: string }>().flightId ?? null;
  const flight = useAgricultureFlight(flightId);
  if (!flightId)
    return <Alert severity="error">Invalid agriculture flight.</Alert>;
  if (flight.isLoading)
    return (
      <Stack role="status" direction="row" spacing={1} p={3}>
        <CircularProgress size={18} />
        <Typography>Loading flight…</Typography>
      </Stack>
    );
  if (flight.isError || !flight.data)
    return <Alert severity="error">Agriculture flight unavailable.</Alert>;
  return (
    <AgricultureAccessibilityBoundary>
      <Stack
        spacing={2}
        sx={{ p: { xs: 1, md: 3 }, maxWidth: 1440, mx: "auto" }}
      >
        <Button
          component={RouterLink}
          to={`/dashboard/agriculture/fields/${flight.data.field_id}`}
          sx={{ alignSelf: "flex-start" }}
        >
          ← Field {flight.data.field_id}
        </Button>
        <div>
          <Typography variant="h4" component="h1">
            Agriculture flight
          </Typography>
          <Typography color="text.secondary">
            {flightId} · {flight.data.status}
          </Typography>
        </div>
        <AgricultureLiveStatusPanel flightId={flightId} active />
      </Stack>
    </AgricultureAccessibilityBoundary>
  );
}
