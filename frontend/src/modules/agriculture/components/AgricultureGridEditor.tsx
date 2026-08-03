import { Alert, Button, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import type { AgriculturePlan } from "../types";
import { AgricultureGeoJsonPreview } from "./AgricultureGeoJsonPreview";

export function AgricultureGridEditor({ plan, disabled, onSave }: { plan: AgriculturePlan; disabled?: boolean; onSave: (route: number[][]) => void }) {
  const [text, setText] = useState("[]");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setText(JSON.stringify((plan.route_geojson.coordinates as number[][] | undefined) ?? [], null, 2)); }, [plan.id, plan.grid_revision, plan.route_geojson]);
  const save = () => { try { const route = JSON.parse(text) as unknown; if (!Array.isArray(route) || route.length < 2 || route.some((point) => !Array.isArray(point) || point.length < 2)) throw new Error("Grid route must contain at least two [longitude, latitude] points."); setError(null); onSave(route as number[][]); } catch (exc) { setError(exc instanceof Error ? exc.message : "Invalid grid route JSON."); } };
  const route = (plan.route_geojson.coordinates as number[][] | undefined) ?? [];
  return <Stack spacing={1}><Typography variant="subtitle1">Survey grid editor</Typography><Typography variant="body2" color="text.secondary">Revision {plan.grid_revision} · {plan.planner_version}. Edit waypoints only inside the field and outside safety zones; the server revalidates both constraints.</Typography>{error ? <Alert severity="error">{error}</Alert> : null}<TextField label="Route waypoints [longitude, latitude]" value={text} onChange={(e) => setText(e.target.value)} multiline minRows={4} fullWidth /><Button variant="outlined" onClick={save} disabled={disabled}>Save grid revision</Button><AgricultureGeoJsonPreview geojson={{ features: [{ type: "Feature", geometry: plan.route_geojson, properties: { id: "planned-grid" } }] }} /><Typography variant="caption" color="text.secondary">Estimated route: {String(plan.estimates.route_m ?? "pending")} m · {String(plan.estimates.segment_count ?? 1)} segment(s) · {route.length} waypoints</Typography></Stack>;
}
