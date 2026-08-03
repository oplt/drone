import {
  Alert,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { Link as RouterLink, useParams } from "react-router-dom";
import { AgricultureAccessibilityBoundary } from "../components/AgricultureAccessibilityBoundary";
import { AgricultureFieldProfile } from "../components/AgricultureFieldProfile";
import { AgricultureFieldBoundaryEditor } from "../components/AgricultureFieldBoundaryEditor";
import { AgricultureFlightPlanner } from "../components/AgricultureFlightPlanner";
import { AgricultureTemporalWorkspace } from "../components/AgricultureTemporalWorkspace";
import { useAgricultureFieldFlights, useAgricultureFields, useAgricultureProfile } from "../hooks";

export default function AgricultureFieldDetailPage() {
  const fieldId = Number(useParams<{ fieldId: string }>().fieldId);
  const profile = useAgricultureProfile(
    Number.isFinite(fieldId) ? fieldId : null,
  );
  const flights = useAgricultureFieldFlights(
    Number.isFinite(fieldId) ? fieldId : null,
  );
  const fields = useAgricultureFields();
  if (!Number.isFinite(fieldId))
    return <Alert severity="error">Invalid agriculture field.</Alert>;
  if (profile.isLoading || flights.isLoading || fields.isLoading)
    return (
      <Stack role="status" direction="row" spacing={1} p={3}>
        <CircularProgress size={18} />
        <Typography>Loading field workspace…</Typography>
      </Stack>
    );
  if (profile.isError || flights.isError || fields.isError)
    return (
      <Alert severity="error">
        Field workspace unavailable. Retry from the field list.
      </Alert>
    );
  const latestFlight = flights.data?.[0];
  const field = fields.data?.find((item) => item.id === fieldId);
  const fieldCoordinates = (field?.geometry_geojson as { coordinates?: number[][][] } | undefined)?.coordinates?.[0] ?? null;
  return (
    <AgricultureAccessibilityBoundary>
      <Stack
        spacing={2}
        sx={{ p: { xs: 2, md: 4 }, maxWidth: 1440, mx: "auto" }}
      >
        <Button
          component={RouterLink}
          to="/dashboard/agriculture/fields"
          sx={{ alignSelf: "flex-start" }}
        >
          ← All agriculture fields
        </Button>
        <div>
          <Typography variant="h4" component="h1">
            Field {fieldId}
          </Typography>
          <Typography color="text.secondary">
            Crop and stage context remain separate from model claims.
          </Typography>
        </div>
        <AgricultureFlightPlanner fieldId={fieldId} fieldPolygon={fieldCoordinates} fieldProfile={profile.data ?? null} />
        <AgricultureFieldBoundaryEditor fieldId={fieldId} />
        {profile.data ? (
          <AgricultureFieldProfile fieldId={fieldId} value={profile.data} />
        ) : null}
        <Stack spacing={1}>
          <Typography variant="h6">Flight history</Typography>
          {flights.data?.length ? (
            flights.data.map((flight) => (
              <Card key={flight.id} variant="outlined">
                <CardActionLink
                  flightId={flight.id}
                  status={flight.status}
                  createdAt={flight.created_at}
                />
              </Card>
            ))
          ) : (
            <Alert severity="info">
              No agriculture flights recorded for this field.
            </Alert>
          )}
        </Stack>
        {latestFlight ? (
          <AgricultureTemporalWorkspace
            fieldId={fieldId}
            currentFlightId={latestFlight.id}
          />
        ) : null}
      </Stack>
    </AgricultureAccessibilityBoundary>
  );
}

function CardActionLink({
  flightId,
  status,
  createdAt,
}: {
  flightId: string;
  status: string;
  createdAt: string;
}) {
  return (
    <CardContent
      component={RouterLink}
      to={`/dashboard/agriculture/flights/${flightId}`}
      sx={{
        display: "block",
        color: "inherit",
        textDecoration: "none",
        "&:focus-visible": {
          outline: "3px solid",
          outlineColor: "primary.main",
        },
      }}
    >
      <Stack
        direction={{ xs: "column", sm: "row" }}
        justifyContent="space-between"
        spacing={1}
      >
        <Typography>{new Date(createdAt).toLocaleString()}</Typography>
        <Typography variant="body2" color="text.secondary">
          {status} · {flightId}
        </Typography>
      </Stack>
    </CardContent>
  );
}
