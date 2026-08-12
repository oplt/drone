import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Card, CardContent, Divider, Stack, TextField, Typography } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useEffect, useMemo, useState } from "react";
import { AgricultureGeoJsonPreview } from "./AgricultureGeoJsonPreview";
import { useAddAgricultureZone, useAgricultureFieldContext, useDeleteAgricultureZone, useUpdateAgricultureBoundary } from "../hooks";
import { polygonRing, validateAgriculturePolygon, type AgriculturePolygon } from "../geometry";
import { AgricultureGeometryMapEditor } from "./AgricultureGeometryMapEditor";

type Polygon = AgriculturePolygon;
const emptyPolygon: Polygon = { type: "Polygon", coordinates: [[]] };

function parseBoundary(value: string): Polygon {
  return validateAgriculturePolygon(JSON.parse(value));
}

export function AgricultureFieldBoundaryEditor({ fieldId }: { fieldId: number }) {
  const context = useAgricultureFieldContext(fieldId);
  const update = useUpdateAgricultureBoundary();
  const addZone = useAddAgricultureZone();
  const removeZone = useDeleteAgricultureZone();
  const [boundaryText, setBoundaryText] = useState(JSON.stringify(emptyPolygon, null, 2));
  const [reason, setReason] = useState("");
  const [zoneType, setZoneType] = useState<"exclusion" | "obstacle">("exclusion");
  const [zoneLon, setZoneLon] = useState("");
  const [zoneLat, setZoneLat] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Hydrate the editor only when the server publishes a new boundary revision.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { if (context.data?.boundary) setBoundaryText(JSON.stringify(context.data.boundary, null, 2)); }, [context.data?.current_revision]);
  const parsed = useMemo(() => { try { return parseBoundary(boundaryText); } catch { return null; } }, [boundaryText]);
  const features = parsed ? [{ type: "Feature", geometry: parsed, properties: { id: "boundary", severity: 0.2 } }, ...(context.data?.zones ?? []).map((zone) => ({ type: "Feature", geometry: zone.geometry, properties: { id: zone.id, severity: zone.zone_type === "obstacle" ? 0.8 : 0.6 } }))] : [];
  const saveBoundary = () => { try { setError(null); update.mutate({ fieldId, boundary: parseBoundary(boundaryText), reason: reason || undefined }); } catch (exc) { setError(exc instanceof Error ? exc.message : "Invalid boundary JSON."); } };
  const addZoneGeometry = (geometry: Record<string, unknown>) => {
    setError(null);
    addZone.mutate({ fieldId, payload: { zone_type: zoneType, geometry, name: zoneType === "exclusion" ? "Flight exclusion" : "Obstacle", kind: zoneType === "obstacle" ? "unknown" : "no-fly", radius_m: zoneType === "obstacle" ? 5 : null, height_m: null, metadata: {} } });
  };
  const saveZone = () => { const lon = Number(zoneLon); const lat = Number(zoneLat); if (!Number.isFinite(lon) || !Number.isFinite(lat)) { setError("Zone longitude and latitude are required."); return; } addZoneGeometry({ type: "Point", coordinates: [lon, lat] }); setZoneLon(""); setZoneLat(""); };
  if (context.isLoading) return <Card variant="outlined"><CardContent><Typography role="status">Loading boundary context…</Typography></CardContent></Card>;
  if (context.isError) return <Alert severity="error">Boundary context unavailable. Retry the field workspace.</Alert>;
  return <Card component="section" variant="outlined" aria-labelledby="boundary-editor-title"><CardContent><Stack spacing={2}>
    <div><Typography id="boundary-editor-title" variant="h6">Field boundary and safety zones</Typography><Typography variant="body2" color="text.secondary">Draw the boundary and safety zones on the map. Every save creates a revision; server validation rejects unsafe geometry.</Typography></div>
    {error ? <Alert severity="error" onClose={() => setError(null)}>{error}</Alert> : null}
    {update.isError || addZone.isError ? <Alert severity="error">{String((update.error ?? addZone.error) instanceof Error ? (update.error ?? addZone.error) : "Save failed")}</Alert> : null}
    <AgricultureGeometryMapEditor
      boundary={polygonRing(parsed)}
      exclusionZones={(context.data?.zones ?? []).filter((zone) => zone.geometry.type === "Polygon").map((zone) => (zone.geometry.coordinates as number[][][])[0] as [number, number][])}
      onBoundaryChange={(ring) => {
        try {
          const next = validateAgriculturePolygon({ type: "Polygon", coordinates: [ring] });
          setBoundaryText(JSON.stringify(next, null, 2));
          setError(null);
        } catch (caught) {
          setError(caught instanceof Error ? caught.message : "Invalid boundary.");
        }
      }}
      onExclusionZone={(ring) => {
        try { addZoneGeometry(validateAgriculturePolygon({ type: "Polygon", coordinates: [ring] })); }
        catch (caught) { setError(caught instanceof Error ? caught.message : "Invalid safety zone."); }
      }}
    />
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}><TextField label="Revision note" value={reason} onChange={(event) => setReason(event.target.value)} fullWidth /><Button variant="contained" onClick={saveBoundary} disabled={update.isPending || !parsed}>Save boundary revision</Button><Button variant="outlined" onClick={() => setBoundaryText(JSON.stringify(context.data?.boundary ?? emptyPolygon, null, 2))}>Undo edits</Button></Stack>
    <Divider />
    <Typography variant="subtitle1">Exclusions and obstacles</Typography>
    <TextField select label="Zone type for next drawing" SelectProps={{ native: true }} value={zoneType} onChange={(event) => setZoneType(event.target.value as "exclusion" | "obstacle")}><option value="exclusion">Exclusion zone</option><option value="obstacle">Obstacle area</option></TextField>
    {(context.data?.zones ?? []).map((zone) => <Stack key={zone.id} direction="row" justifyContent="space-between" alignItems="center" sx={{ minHeight: 48 }}><Typography>{zone.zone_type === "exclusion" ? "Exclusion" : "Obstacle"} · {zone.kind} · revision {zone.revision}</Typography><Button color="error" onClick={() => { if (window.confirm("Remove this zone from the field?")) removeZone.mutate({ fieldId, zoneId: zone.id }); }}>Remove</Button></Stack>)}
    <Accordion>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>Advanced coordinates and GeoJSON</AccordionSummary>
      <AccordionDetails><Stack spacing={1}>
        <TextField label="Boundary GeoJSON (EPSG:4326)" multiline minRows={5} value={boundaryText} onChange={(event) => setBoundaryText(event.target.value)} fullWidth inputProps={{ "aria-describedby": "boundary-help" }} />
        <Typography id="boundary-help" variant="caption" color="text.secondary">Coordinates are [longitude, latitude].</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}><TextField label="Longitude" inputMode="decimal" value={zoneLon} onChange={(event) => setZoneLon(event.target.value)} /><TextField label="Latitude" inputMode="decimal" value={zoneLat} onChange={(event) => setZoneLat(event.target.value)} /><Button variant="outlined" onClick={saveZone} disabled={addZone.isPending}>Add point zone</Button></Stack>
      </Stack></AccordionDetails>
    </Accordion>
    {parsed ? <Box><AgricultureGeoJsonPreview geojson={{ features }} /><Typography variant="caption" color="text.secondary">Area: {context.data?.area_ha?.toFixed(2) ?? "pending"} ha · boundary revision {context.data?.current_revision ?? 0}</Typography></Box> : null}
  </Stack></CardContent></Card>;
}
