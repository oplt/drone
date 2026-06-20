import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import {
  createPropertyPatrolSite,
  createPropertyPatrolTemplate,
  listPropertyPatrolIncidents,
  listPropertyPatrolSites,
  listPropertyPatrolTemplates,
  previewPropertyPatrolRoute,
  startPropertyPatrolMission,
  type PatrolTemplate,
  type PropertyPatrolSite,
  type RoutePreview,
} from "../api/propertyPatrolApi";
import { getSessionMarker } from "../../session/sessionCookies";

const SAMPLE_POLYGON = {
  type: "Polygon" as const,
  coordinates: [
    [
      [5.12, 50.12],
      [5.124, 50.12],
      [5.124, 50.123],
      [5.12, 50.123],
      [5.12, 50.12],
    ],
  ],
};

export default function PropertyPatrolPage() {
  const token = getSessionMarker();
  const [sites, setSites] = useState<PropertyPatrolSite[]>([]);
  const [templates, setTemplates] = useState<PatrolTemplate[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<number | "">("");
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | "">("");
  const [siteName, setSiteName] = useState("Main Property");
  const [templateName, setTemplateName] = useState("Perimeter Patrol");
  const [mode, setMode] = useState<PatrolTemplate["patrol_mode"]>("perimeter");
  const [triggerBehavior, setTriggerBehavior] = useState<PatrolTemplate["trigger_behavior"]>("approval_required");
  const [routePreview, setRoutePreview] = useState<RoutePreview | null>(null);
  const [incidents, setIncidents] = useState<Awaited<ReturnType<typeof listPropertyPatrolIncidents>>>([]);
  const [error, setError] = useState<string | null>(null);
  const [creatingSite, setCreatingSite] = useState(false);
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const [previewingRoute, setPreviewingRoute] = useState(false);
  const [startingMission, setStartingMission] = useState(false);
  const selectedSite = useMemo(
    () => sites.find((site) => site.id === selectedSiteId) ?? null,
    [selectedSiteId, sites],
  );

  async function refresh(siteId = selectedSiteId) {
    const loadedSites = await listPropertyPatrolSites(token);
    setSites(loadedSites);
    const nextSiteId = siteId || loadedSites[0]?.id || "";
    setSelectedSiteId(nextSiteId);
    if (nextSiteId) {
      const [loadedTemplates, loadedIncidents] = await Promise.all([
        listPropertyPatrolTemplates(nextSiteId, token),
        listPropertyPatrolIncidents(nextSiteId, token),
      ]);
      setTemplates(loadedTemplates);
      setSelectedTemplateId(loadedTemplates[0]?.id || "");
      setIncidents(loadedIncidents);
    }
  }

  useEffect(() => {
    void refresh().catch((err) => setError(err instanceof Error ? err.message : String(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreateSite() {
    try {
      setCreatingSite(true);
      setError(null);
      const site = await createPropertyPatrolSite(
        {
          name: siteName.trim() || "Main Property",
          description: "Property Patrol Mission sample site",
          property_boundary: SAMPLE_POLYGON,
          flight_safe_area: SAMPLE_POLYGON,
          no_fly_zones: [],
          privacy_zones: [],
          emergency_landing_zones: [],
          default_home_position: { lat: 50.1205, lon: 5.1205, alt: 0 },
          default_altitude_m: 30,
        },
        token,
      );
      await refresh(site.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreatingSite(false);
    }
  }

  async function handleCreateTemplate() {
    if (!selectedSiteId) return;
    try {
      setCreatingTemplate(true);
      setError(null);
      const template = await createPropertyPatrolTemplate(
        {
          site_id: selectedSiteId,
          name: templateName.trim() || "Perimeter Patrol",
          patrol_mode: mode,
          altitude_m: 30,
          speed_mps: 6,
          boundary_offset_m: 15,
          grid_spacing_m: 40,
          overlap_percent: 50,
          camera_direction: "inward",
          camera_gimbal_pitch_deg: 35,
          schedule_interval_minutes: null,
          max_mission_duration_minutes: 25,
          min_battery_return_percent: 30,
          trigger_behavior: triggerBehavior,
          ai_detection_enabled: true,
          llm_summary_enabled: false,
          privacy_blur_faces: true,
          privacy_blur_license_plates: true,
          event_clip_recording_only: true,
          retention_hours_or_days: "72h",
        },
        token,
      );
      await refresh(selectedSiteId);
      setSelectedTemplateId(template.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreatingTemplate(false);
    }
  }

  async function handlePreview() {
    if (!selectedSiteId) return;
    try {
      setPreviewingRoute(true);
      setError(null);
      const preview = await previewPropertyPatrolRoute(
        {
          site_id: selectedSiteId,
          template_id: selectedTemplateId || null,
          patrol_mode: mode,
        },
        token,
      );
      setRoutePreview(preview);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewingRoute(false);
    }
  }

  async function handleStart() {
    if (!selectedSiteId) return;
    try {
      setStartingMission(true);
      setError(null);
      await startPropertyPatrolMission(
        { site_id: selectedSiteId, template_id: selectedTemplateId || null, mission_type: "manual" },
        token,
      );
      await refresh(selectedSiteId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStartingMission(false);
    }
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          alignItems={{ xs: "stretch", sm: "flex-start" }}
          justifyContent="space-between"
        >
          <Box>
            <Typography variant="h4">Property Patrol Mission</Typography>
            <Typography color="text.secondary">
              Configure bounded patrol sites, preview validated routes, review incidents, and keep sensor-triggered flights behind policy checks.
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={<AddRoundedIcon />}
            onClick={() => void handleCreateSite()}
            disabled={creatingSite}
            sx={{ minWidth: 156, flexShrink: 0 }}
          >
            {creatingSite ? "Creating..." : "Create site"}
          </Button>
        </Stack>
        {error ? <Alert severity="error" onClose={() => setError(null)}>{error}</Alert> : null}

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="h6">Sites</Typography>
            <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ xs: "stretch", md: "center" }}>
              <TextField label="Site name" value={siteName} onChange={(event) => setSiteName(event.target.value)} sx={{ minWidth: { md: 260 } }} />
              <Button
                variant="contained"
                startIcon={<AddRoundedIcon />}
                onClick={() => void handleCreateSite()}
                disabled={creatingSite}
                sx={{ minWidth: 148, flexShrink: 0 }}
              >
                {creatingSite ? "Creating..." : "Create site"}
              </Button>
              <FormControl sx={{ minWidth: 220 }}>
                <InputLabel>Active site</InputLabel>
                <Select label="Active site" value={selectedSiteId} onChange={(event) => void refresh(Number(event.target.value))}>
                  {sites.map((site) => <MenuItem key={site.id} value={site.id}>{site.name}</MenuItem>)}
                </Select>
              </FormControl>
            </Stack>
            {selectedSite ? (
              <Typography variant="body2">
                Safe polygon stored as GeoJSON. No-fly zones: {selectedSite.no_fly_zones.length}. Privacy zones: {selectedSite.privacy_zones.length}.
              </Typography>
            ) : <Typography color="text.secondary">No sites yet.</Typography>}
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="h6">Template And Route Preview</Typography>
            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
              <TextField label="Template name" value={templateName} onChange={(event) => setTemplateName(event.target.value)} />
              <FormControl sx={{ minWidth: 160 }}>
                <InputLabel>Mode</InputLabel>
                <Select label="Mode" value={mode} onChange={(event) => setMode(event.target.value as PatrolTemplate["patrol_mode"])}>
                  <MenuItem value="perimeter">Perimeter</MenuItem>
                  <MenuItem value="grid">Grid</MenuItem>
                  <MenuItem value="adaptive">Adaptive</MenuItem>
                </Select>
              </FormControl>
              <FormControl sx={{ minWidth: 220 }}>
                <InputLabel>Trigger behavior</InputLabel>
                <Select label="Trigger behavior" value={triggerBehavior} onChange={(event) => setTriggerBehavior(event.target.value as PatrolTemplate["trigger_behavior"])}>
                  <MenuItem value="notify_only">Notify only</MenuItem>
                  <MenuItem value="approval_required">Approval required</MenuItem>
                  <MenuItem value="auto_dispatch">Auto dispatch</MenuItem>
                </Select>
              </FormControl>
              <Button variant="outlined" disabled={!selectedSiteId || creatingTemplate} onClick={() => void handleCreateTemplate()}>
                {creatingTemplate ? "Saving..." : "Save Template"}
              </Button>
              <Button variant="outlined" disabled={!selectedSiteId || previewingRoute} onClick={() => void handlePreview()}>
                {previewingRoute ? "Previewing..." : "Preview Route"}
              </Button>
              <Button variant="contained" color="warning" disabled={!selectedSiteId || startingMission} onClick={() => void handleStart()}>
                {startingMission ? "Starting..." : "Start"}
              </Button>
            </Stack>
            <Stack direction="row" spacing={1} flexWrap="wrap">
              {templates.map((template) => (
                <Chip
                  key={template.id}
                  label={`${template.name} · ${template.patrol_mode}`}
                  color={template.id === selectedTemplateId ? "primary" : "default"}
                  onClick={() => setSelectedTemplateId(template.id)}
                />
              ))}
            </Stack>
            {triggerBehavior === "auto_dispatch" ? <Alert severity="warning">Auto-dispatch still runs policy and preflight validation before movement.</Alert> : null}
            {routePreview ? (
              <Alert severity={routePreview.validation.ok ? "success" : "error"}>
                {routePreview.waypoints.length} waypoints. {routePreview.validation.errors.length} errors. {routePreview.validation.warnings.length} warnings.
              </Alert>
            ) : null}
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="h6">Incidents</Typography>
          <Divider sx={{ my: 1 }} />
          <Stack spacing={1}>
            {incidents.length === 0 ? <Typography color="text.secondary">No incidents.</Typography> : null}
            {incidents.map((incident) => (
              <Stack key={incident.id} spacing={0.5}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip label={incident.status} />
                  <Typography>{incident.event_type}</Typography>
                  {incident.llm_summary ? (
                    <Chip size="small" color="primary" variant="outlined" label="AI summary" />
                  ) : null}
                </Stack>
                <Typography color="text.secondary" variant="body2">
                  {incident.llm_summary || incident.operator_notes || "No summary"}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Paper>
      </Stack>
    </Box>
  );
}
