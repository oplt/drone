import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  CircularProgress,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { AgricultureAccessibilityBoundary } from "../components/AgricultureAccessibilityBoundary";
import { AgricultureGeoJsonPreview } from "../components/AgricultureGeoJsonPreview";
import { AgricultureAlertCenter } from "../components/AgricultureAlertCenter";
import { AgricultureFieldCreateCard } from "../components/AgricultureFieldCreateCard";
import { useAgricultureFields } from "../hooks";

export default function AgricultureFieldListPage() {
  const fields = useAgricultureFields();
  const fieldRows = fields.data ?? [];
  const features = fieldRows.map((field) => ({
    type: "Feature",
    geometry: field.geometry_geojson,
    properties: { id: field.id },
  }));
  return (
    <AgricultureAccessibilityBoundary>
      <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 1440, mx: "auto" }}>
        <Stack spacing={2}>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            justifyContent="space-between"
            spacing={1}
          >
            <div>
              <Typography variant="h4" component="h1">
                Agriculture fields
              </Typography>
              <Typography color="text.secondary">
                Field profiles, crop context, health summaries and flight
                history.
              </Typography>
            </div>
            <Button
              component={RouterLink}
              to="/dashboard/field"
              variant="contained"
            >
              Open field planner
            </Button>
          </Stack>
          <AgricultureAlertCenter />
          <AgricultureFieldCreateCard />
          {fields.isLoading ? (
            <Stack
              role="status"
              direction="row"
              spacing={1}
              alignItems="center"
            >
              <CircularProgress size={18} />
              <Typography>Loading fields…</Typography>
            </Stack>
          ) : fields.isError ? (
            <Alert
              severity="error"
              action={
                <Button onClick={() => void fields.refetch()}>Retry</Button>
              }
            >
              Agriculture fields unavailable.
            </Alert>
          ) : fieldRows.length === 0 ? (
            <Alert severity="info">
              No agriculture fields yet. Create a field in the planner, then
              return here.
            </Alert>
          ) : (
            <>
              <AgricultureGeoJsonPreview geojson={{ features }} />
              <Grid container spacing={2}>
                {fieldRows.map((field) => (
                  <Grid key={field.id} size={{ xs: 12, sm: 6, lg: 4 }}>
                    <Card variant="outlined">
                      <CardActionArea
                        component={RouterLink}
                        to={`/dashboard/agriculture/fields/${field.id}`}
                      >
                        <CardContent>
                          <Typography variant="h6">{field.name}</Typography>
                          <Typography variant="body2" color="text.secondary">
                            {field.area_ha == null
                              ? "Area pending"
                              : `${field.area_ha.toFixed(2)} ha`}{" "}
                            · Field {field.id}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {field.profile.crop_type ?? "Crop not set"} ·{" "}
                            {field.profile.growth_stage ?? "Stage not set"}
                          </Typography>
                          <Typography
                            variant="caption"
                            display="block"
                            color="text.secondary"
                          >
                            Latest health:{" "}
                            {String(
                              field.latest_flight?.quality_summary?.status ??
                                "pending",
                            )}{" "}
                            ·{" "}
                            {field.latest_flight
                              ? field.latest_flight.status
                              : "No flight"}
                          </Typography>
                        </CardContent>
                      </CardActionArea>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </>
          )}
        </Stack>
      </Box>
    </AgricultureAccessibilityBoundary>
  );
}
