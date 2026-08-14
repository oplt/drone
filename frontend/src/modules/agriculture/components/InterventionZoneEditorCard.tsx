import { Alert, Button, Chip, Divider, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { editableZoneRing, ringZoneGeometry } from "../interventionZoneGeometry";
import { useAgricultureInterventionZoneAudit, useReviewAgricultureInterventionZone, useUpdateAgricultureInterventionZone, type AgricultureInterventionZone } from "../workflows/interventionZones";
import { AgricultureGeometryMapEditor } from "./AgricultureGeometryMapEditor";

export function InterventionZoneEditorCard({ zone }: { zone: AgricultureInterventionZone }) {
  const [name, setName] = useState(zone.name);
  const [category, setCategory] = useState(zone.category);
  const [geometry, setGeometry] = useState(zone.geometry_geojson);
  const [note, setNote] = useState("");
  const update = useUpdateAgricultureInterventionZone();
  const review = useReviewAgricultureInterventionZone();
  const audit = useAgricultureInterventionZoneAudit(zone.id);
  const ring = editableZoneRing(geometry);
  const immutable = zone.status !== "proposed";

  return (
    <Stack spacing={1.25}>
      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
        <Chip size="small" color={zone.status === "approved" ? "success" : zone.status === "rejected" ? "error" : "warning"} label={zone.status} />
        <Chip size="small" variant="outlined" label={`${zone.area_m2.toFixed(1)} m²`} />
        <Chip size="small" variant="outlined" label={`Revision ${zone.revision}`} />
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField size="small" label="Zone name" value={name} onChange={(event) => setName(event.target.value)} disabled={immutable} fullWidth />
        <TextField size="small" label="Category" value={category} onChange={(event) => setCategory(event.target.value)} disabled={immutable} fullWidth />
      </Stack>
      {!immutable ? (
        <>
          {geometry.type === "MultiPolygon" ? (
            <Alert severity="info">This proposal has separate polygons. Draw a replacement polygon below to consolidate it, or keep the generated geometry unchanged.</Alert>
          ) : null}
          <AgricultureGeometryMapEditor
            boundary={ring}
            onBoundaryChange={(next) => setGeometry(ringZoneGeometry(next))}
            height={280}
          />
          <Button
            variant="outlined"
            disabled={!name.trim() || !category.trim() || !geometry.type || update.isPending}
            onClick={() => update.mutate({ zone, payload: { expected_revision: zone.revision, name: name.trim(), category: category.trim(), geometry_geojson: geometry } })}
          >
            {update.isPending ? "Saving…" : "Save geometry and details"}
          </Button>
        </>
      ) : null}
      {update.isError ? <Alert severity="error">Zone save failed. Refresh if another reviewer changed this revision.</Alert> : null}
      <Divider />
      <Typography variant="caption" color="text.secondary">
        Sources: {zone.source_observation_ids.length} confirmed observation(s) · {zone.evidence_ids.length} evidence item(s) · models {zone.model_versions.join(", ") || "unrecorded"}
      </Typography>
      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
        {zone.source_observation_ids.map((id) => (
          <Button key={id} component={RouterLink} target="_blank" size="small" to={`/dashboard/agriculture/analysis/${zone.run_id}?observation=${encodeURIComponent(id)}&review=evidence`}>
            Open source {id.slice(0, 8)}
          </Button>
        ))}
      </Stack>
      {!immutable ? (
        <>
          <TextField size="small" label="Approval rationale" value={note} onChange={(event) => setNote(event.target.value)} multiline minRows={2} required />
          <Stack direction="row" spacing={1}>
            <Button color="success" variant="contained" disabled={!note.trim() || review.isPending} onClick={() => review.mutate({ zone, status: "approved", note: note.trim() })}>Approve zone</Button>
            <Button color="error" disabled={!note.trim() || review.isPending} onClick={() => review.mutate({ zone, status: "rejected", note: note.trim() })}>Reject zone</Button>
          </Stack>
          <Alert severity="warning">This zone is not operational and cannot be exported until explicitly approved.</Alert>
        </>
      ) : (
        <Alert severity={zone.status === "approved" ? "success" : "info"}>
          {zone.status === "approved" ? "Approved for downstream action/export; this does not execute treatment." : "Rejected zones remain only in audit history."}
        </Alert>
      )}
      {review.isError ? <Alert severity="error">Review failed because the zone or its source confirmations changed.</Alert> : null}
      <Typography variant="caption" color="text.secondary">
        Reviewer {zone.reviewed_by_user_id ?? "pending"} · audit {audit.isLoading ? "loading…" : `${audit.data?.length ?? 0} event(s)`}
      </Typography>
    </Stack>
  );
}
