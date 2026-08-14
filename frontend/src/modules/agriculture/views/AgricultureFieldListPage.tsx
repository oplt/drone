import { useMemo, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Drawer,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { Link as RouterLink } from "react-router-dom";
import { AgricultureAccessibilityBoundary } from "../components/AgricultureAccessibilityBoundary";
import { AgricultureGeoJsonPreview } from "../components/AgricultureGeoJsonPreview";
import { AgricultureAlertCenter } from "../components/AgricultureAlertCenter";
import { AgricultureFieldSetupWizard } from "../components/AgricultureFieldSetupWizard";
import { useAgricultureFields } from "../hooks";
import { FeatureState } from "../../../shared/ui/FeatureState";

type SortKey = "name" | "health" | "flight";

export default function AgricultureFieldListPage() {
  const fields = useAgricultureFields();
  const fieldRows = useMemo(() => fields.data ?? [], [fields.data]);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [wizardOpen, setWizardOpen] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = fieldRows.filter((field) => {
      if (!q) return true;
      const crop = String(field.profile.crop_type ?? "").toLowerCase();
      const name = String(field.name ?? "").toLowerCase();
      return name.includes(q) || crop.includes(q) || String(field.id).includes(q);
    });
    const healthRank = (status: unknown) => {
      const s = String(status ?? "pending").toLowerCase();
      if (s.includes("critical") || s.includes("fail")) return 0;
      if (s.includes("warn")) return 1;
      if (s.includes("ok") || s.includes("good") || s.includes("pass")) return 3;
      return 2;
    };
    return [...rows].sort((a, b) => {
      if (sortKey === "name") return a.name.localeCompare(b.name);
      if (sortKey === "health") {
        return (
          healthRank(a.latest_flight?.quality_summary?.status) -
          healthRank(b.latest_flight?.quality_summary?.status)
        );
      }
      const aT = a.latest_flight?.created_at
        ? new Date(a.latest_flight.created_at).getTime()
        : 0;
      const bT = b.latest_flight?.created_at
        ? new Date(b.latest_flight.created_at).getTime()
        : 0;
      return bT - aT;
    });
  }, [fieldRows, query, sortKey]);

  const features = filtered.map((field) => ({
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
                Find fields quickly, then open setup or planner when needed.
              </Typography>
            </div>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button variant="outlined" onClick={() => setWizardOpen(true)}>
                New field setup
              </Button>
              <Button
                component={RouterLink}
                to="/dashboard/field"
                variant="contained"
              >
                Open field planner
              </Button>
            </Stack>
          </Stack>

          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
            <TextField
              size="small"
              label="Search name or crop"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              sx={{ flex: 1, maxWidth: 420 }}
            />
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel id="field-sort-label">Sort</InputLabel>
              <Select
                labelId="field-sort-label"
                label="Sort"
                value={sortKey}
                onChange={(event) => setSortKey(event.target.value as SortKey)}
              >
                <MenuItem value="name">Name</MenuItem>
                <MenuItem value="flight">Latest flight</MenuItem>
                <MenuItem value="health">Health status</MenuItem>
              </Select>
            </FormControl>
          </Stack>

          <Accordion disableGutters>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="subtitle2">Operational alerts</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <AgricultureAlertCenter />
            </AccordionDetails>
          </Accordion>

          <FeatureState
            loading={fields.isLoading}
            error={fields.isError ? "Agriculture fields unavailable." : null}
            onRetry={() => void fields.refetch()}
            empty={
              !fields.isLoading && !fields.isError && fieldRows.length === 0
                ? {
                    title: "No agriculture fields yet",
                    description:
                      "Create a field in setup or the planner, then return here.",
                    action: (
                      <Stack direction="row" spacing={1}>
                        <Button
                          variant="contained"
                          onClick={() => setWizardOpen(true)}
                        >
                          New field setup
                        </Button>
                        <Button
                          component={RouterLink}
                          to="/dashboard/field"
                          variant="outlined"
                        >
                          Open field planner
                        </Button>
                      </Stack>
                    ),
                  }
                : undefined
            }
          >
            <Stack spacing={2}>
              {query && filtered.length === 0 ? (
                <Typography color="text.secondary">
                  No fields match “{query}”.
                </Typography>
              ) : null}
              <Grid container spacing={2}>
                {filtered.map((field) => (
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
              <Accordion disableGutters>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">Map overview</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <AgricultureGeoJsonPreview geojson={{ features }} />
                </AccordionDetails>
              </Accordion>
            </Stack>
          </FeatureState>
        </Stack>

        <Drawer
          anchor="right"
          open={wizardOpen}
          onClose={() => setWizardOpen(false)}
          PaperProps={{ sx: { width: { xs: "100%", sm: 420 } } }}
        >
          <Box sx={{ p: 2 }}>
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ mb: 2 }}
            >
              <Typography variant="h6">Field setup</Typography>
              <Button size="small" onClick={() => setWizardOpen(false)}>
                Close
              </Button>
            </Stack>
            <AgricultureFieldSetupWizard />
          </Box>
        </Drawer>
      </Box>
    </AgricultureAccessibilityBoundary>
  );
}
