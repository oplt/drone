import { Alert, Button, Checkbox, FormControlLabel, Paper, Stack, TextField, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import { useAgricultureObservationPage } from "../hooks";
import { useAgricultureInterventionZones, useCreateAgricultureInterventionZone } from "../workflows/interventionZones";
import { AgricultureAnalysisMap } from "./AgricultureAnalysisMap";
import { InterventionZoneEditorCard } from "./InterventionZoneEditorCard";

const EMPTY = { type: "FeatureCollection", features: [] };
const EMPTY_ZONES: never[] = [];

export function AgricultureInterventionZoneWorkspace({ runId }: { runId: string }) {
  const observations = useAgricultureObservationPage(runId, { limit: 500 });
  const zones = useAgricultureInterventionZones(runId);
  const create = useCreateAgricultureInterventionZone();
  const [selectedObservationIds, setSelectedObservationIds] = useState<string[]>([]);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("scouting");
  const confirmed = (observations.data?.items ?? []).filter(
    (row) => row.review_state === "confirmed" && ["Polygon", "MultiPolygon"].includes(String(row.geometry_geojson.type)),
  );
  const zoneRows = zones.data ?? EMPTY_ZONES;
  const selectedZone = zoneRows.find((zone) => zone.id === selectedZoneId) ?? zoneRows[0] ?? null;
  const zoneGeojson = useMemo(() => ({
    type: "FeatureCollection",
    features: zoneRows.map((zone) => ({
      type: "Feature",
      geometry: zone.geometry_geojson,
      properties: { id: zone.id, zone_id: zone.id, name: zone.name, category: zone.category, status: zone.status },
    })),
  }), [zoneRows]);

  const toggleSource = (id: string) => setSelectedObservationIds((current) =>
    current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);

  return (
    <Paper component="section" aria-labelledby="intervention-zone-heading" variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1.5}>
        <div>
          <Typography id="intervention-zone-heading" variant="subtitle2">Intervention zones</Typography>
          <Typography variant="caption" color="text.secondary">Build editable proposals only from confirmed, georeferenced polygon findings.</Typography>
        </div>
        {observations.data && observations.data.total > 500 ? <Alert severity="info">Showing the first 500 findings. Narrow review scope before building zones from larger runs.</Alert> : null}
        {confirmed.length ? (
          <Stack component="fieldset" sx={{ border: 1, borderColor: "divider", borderRadius: 1, m: 0, p: 1, maxHeight: 190, overflow: "auto" }}>
            <Typography component="legend" variant="caption" fontWeight={700}>Confirmed source observations</Typography>
            {confirmed.map((row) => (
              <FormControlLabel key={row.id} control={<Checkbox checked={selectedObservationIds.includes(row.id)} onChange={() => toggleSource(row.id)} />} label={`${row.observation_type.replaceAll("_", " ")} · ${row.area_m2?.toFixed(1) ?? "?"} m² · ${row.id.slice(0, 8)}`} />
            ))}
          </Stack>
        ) : <Alert severity="info">Confirm at least one polygon observation in Findings before proposing a zone.</Alert>}
        <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
          <TextField size="small" label="Zone name" value={name} onChange={(event) => setName(event.target.value)} fullWidth />
          <TextField size="small" label="Category" value={category} onChange={(event) => setCategory(event.target.value)} fullWidth />
          <Button
            variant="contained"
            disabled={!name.trim() || !category.trim() || !selectedObservationIds.length || create.isPending}
            onClick={() => create.mutate({ runId, payload: { name: name.trim(), category: category.trim(), source_observation_ids: selectedObservationIds } }, { onSuccess: (zone) => { setSelectedZoneId(zone.id); setSelectedObservationIds([]); setName(""); } })}
            sx={{ minWidth: 150, minHeight: 44 }}
          >
            {create.isPending ? "Proposing…" : "Propose zone"}
          </Button>
        </Stack>
        {create.isError ? <Alert severity="error">Zone proposal failed. Every source must still be confirmed and have valid field geometry.</Alert> : null}
        {zoneRows.length ? (
          <>
            <AgricultureAnalysisMap observations={EMPTY} interventionZones={zoneGeojson} selectedId={selectedZone?.id} onSelect={setSelectedZoneId} height={340} initialVisibility={{ severity: false, observations: false }} />
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap aria-label="Intervention zone list">
              {zoneRows.map((zone) => <Button key={zone.id} size="small" variant={zone.id === selectedZone?.id ? "contained" : "outlined"} onClick={() => setSelectedZoneId(zone.id)}>{zone.name} · {zone.status}</Button>)}
            </Stack>
            {selectedZone ? <InterventionZoneEditorCard key={`${selectedZone.id}:${selectedZone.revision}`} zone={selectedZone} /> : null}
          </>
        ) : <Typography variant="caption" color="text.secondary">No intervention-zone proposals yet.</Typography>}
      </Stack>
    </Paper>
  );
}
