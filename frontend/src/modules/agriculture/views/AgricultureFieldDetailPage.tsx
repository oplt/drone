import {
  Alert,
  Button,
  Card,
  CardContent,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { AgricultureAccessibilityBoundary } from "../components/AgricultureAccessibilityBoundary";
import { AgricultureFieldProfile } from "../components/AgricultureFieldProfile";
import { AgricultureFieldBoundaryEditor } from "../components/AgricultureFieldBoundaryEditor";
import { AgricultureFlightPlanner } from "../components/AgricultureFlightPlanner";
import { AgricultureTemporalWorkspace } from "../components/AgricultureTemporalWorkspace";
import { useAgricultureFieldFlights, useAgricultureFields, useAgricultureProfile } from "../hooks";
import { FeatureState } from "../../../shared/ui/FeatureState";

export default function AgricultureFieldDetailPage() {
  const fieldId = Number(useParams<{ fieldId: string }>().fieldId);
  const profile = useAgricultureProfile(
    Number.isFinite(fieldId) ? fieldId : null,
  );
  const flights = useAgricultureFieldFlights(
    Number.isFinite(fieldId) ? fieldId : null,
  );
  const fields = useAgricultureFields();
  const [tab, setTab] = useState(0);
  const comparableCount = useMemo(
    () => Math.max(0, (flights.data?.length ?? 0) - 1),
    [flights.data],
  );

  if (!Number.isFinite(fieldId))
    return <Alert severity="error">Invalid agriculture field.</Alert>;

  const latestFlight = flights.data?.[0];
  const field = fields.data?.find((item) => item.id === fieldId);
  const fieldCoordinates =
    (field?.geometry_geojson as { coordinates?: number[][][] } | undefined)
      ?.coordinates?.[0] ?? null;

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
            Setup, flights, and multi-flight compare — one job per tab.
          </Typography>
        </div>

        <FeatureState
          loading={profile.isLoading || flights.isLoading || fields.isLoading}
          error={
            profile.isError || flights.isError || fields.isError
              ? "Field workspace unavailable. Retry from the field list."
              : null
          }
          onRetry={() => {
            void profile.refetch();
            void flights.refetch();
            void fields.refetch();
          }}
        >
          <Tabs
            value={tab}
            onChange={(_e, value: number) => setTab(value)}
            aria-label="Field workspace sections"
            variant="scrollable"
            allowScrollButtonsMobile
          >
            <Tab label="Setup" id="field-tab-0" aria-controls="field-panel-0" />
            <Tab label="Flights" id="field-tab-1" aria-controls="field-panel-1" />
            <Tab
              label="Compare"
              id="field-tab-2"
              aria-controls="field-panel-2"
              disabled={comparableCount < 1}
            />
          </Tabs>

          <Stack
            role="tabpanel"
            id={`field-panel-${tab}`}
            aria-labelledby={`field-tab-${tab}`}
            spacing={2}
          >
            {tab === 0 ? (
              <>
                <AgricultureFlightPlanner
                  fieldId={fieldId}
                  fieldPolygon={fieldCoordinates}
                  fieldProfile={profile.data ?? null}
                />
                <AgricultureFieldBoundaryEditor fieldId={fieldId} />
                {profile.data ? (
                  <AgricultureFieldProfile fieldId={fieldId} value={profile.data} />
                ) : null}
              </>
            ) : null}

            {tab === 1 ? (
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
            ) : null}

            {tab === 2 && latestFlight ? (
              <AgricultureTemporalWorkspace
                fieldId={fieldId}
                currentFlightId={latestFlight.id}
              />
            ) : null}

            {tab === 2 && !latestFlight ? (
              <Alert severity="info">
                Compare needs at least two flights. Record another flight first.
              </Alert>
            ) : null}
          </Stack>
        </FeatureState>
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
      <Typography variant="subtitle1">{flightId}</Typography>
      <Typography variant="body2" color="text.secondary">
        {status} · {new Date(createdAt).toLocaleString()}
      </Typography>
    </CardContent>
  );
}
