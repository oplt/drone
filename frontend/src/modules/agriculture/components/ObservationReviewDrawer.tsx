import { Alert, Button, Chip, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useAgricultureObservationAudits, useAgricultureObservationFeedback, useAssignAgricultureObservation, useCreateAgricultureObservationAlert, useDecideAgricultureObservationFeedback, useReviewAgricultureObservation, useSubmitAgricultureObservationFeedback } from "../hooks";
import type { AgricultureObservation } from "../types";
import { EvidenceFrameCarousel } from "./EvidenceFrameCarousel";
import { AssignReviewerDialog } from "./AssignReviewerDialog";

export function ObservationReviewDrawer({
  observation,
}: {
  observation: AgricultureObservation | null;
}) {
  const [note, setNote] = useState("");
  const [correctionLabel, setCorrectionLabel] = useState("");
  const [correctionSeverity, setCorrectionSeverity] = useState("");
  const [assignOpen, setAssignOpen] = useState(false);
  const review = useReviewAgricultureObservation();
  const assign = useAssignAgricultureObservation();
  const feedback = useAgricultureObservationFeedback(observation?.id ?? null);
  const submitFeedback = useSubmitAgricultureObservationFeedback();
  const decideFeedback = useDecideAgricultureObservationFeedback();
  const createAlert = useCreateAgricultureObservationAlert();
  const audit = useAgricultureObservationAudits(observation?.id ?? null);
  if (!observation) return null;
  return (
    <Stack
      component="aside"
      aria-labelledby="observation-review-drawer-heading"
      spacing={1}
      sx={{ flex: 1 }}
    >
      <Typography id="observation-review-drawer-heading" variant="subtitle2">
        Observation review
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Chip
          size="small"
          label={`Severity ${Math.round(observation.severity * 100)}%`}
        />
        <Chip
          size="small"
          label={`Confidence ${Math.round(observation.confidence * 100)}%`}
        />
        <Chip
          size="small"
          label={
            observation.georef_status === "resolved"
              ? "Georeferenced"
              : "Location unresolved"
          }
          color={
            observation.georef_status === "resolved" ? "success" : "warning"
          }
        />
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Evidence and candidate-only limitations must be reviewed before confirmation. Corrections are submitted as immutable feedback and only change the canonical finding after an explicit decision.
      </Typography>
      <Typography variant="caption">
        Detected: {observation.first_detected ?? "unknown"} →{" "}
        {observation.last_detected ?? "unknown"} · Model:{" "}
        {observation.model_version ?? "fallback/unknown"}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Claim status: candidate-only. Confirmed model version: {observation.model_version ?? "none"}. {String(observation.uncertainty?.policy ?? "Review evidence before using this output operationally.")}
      </Typography>
      <TextField
        size="small"
        label="Review note"
        multiline
        minRows={2}
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button
          size="small"
          variant="contained"
          onClick={() =>
            review.mutate({
              id: observation.id,
              payload: { status: "confirmed", note },
            })
          }
        >
          Confirm
        </Button>
        <Button
          size="small"
          color="error"
          onClick={() =>
            review.mutate({
              id: observation.id,
              payload: { status: "rejected", note },
            })
          }
        >
          Reject
        </Button>
        <Button
          size="small"
          onClick={() =>
            review.mutate({
              id: observation.id,
              payload: {
                status: "relabelled",
                label: "needs_agronomist_review",
                note,
              },
            })
          }
        >
          Relabel
        </Button>
      </Stack>
      <Button size="small" variant="outlined" disabled={assign.isPending} onClick={() => setAssignOpen(true)}>Assign reviewer</Button>
      <AssignReviewerDialog
        open={assignOpen}
        pending={assign.isPending}
        onClose={() => setAssignOpen(false)}
        onAssign={(userId, dueAt) => assign.mutate({ id: observation.id, payload: { assigned_to_user_id: userId, review_due_at: dueAt, reason: "Signed-in reviewer assignment" } }, { onSuccess: () => setAssignOpen(false) })}
      />
      <Stack spacing={0.75} sx={{ p: 1, border: 1, borderColor: "divider", borderRadius: 1 }}>
        <Typography variant="caption" fontWeight={700}>Reviewer correction or disagreement</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField size="small" label="Corrected class" value={correctionLabel} onChange={(event) => setCorrectionLabel(event.target.value)} />
          <TextField size="small" label="Corrected severity 0–1" value={correctionSeverity} onChange={(event) => setCorrectionSeverity(event.target.value)} inputProps={{ inputMode: "decimal", min: 0, max: 1 }} />
        </Stack>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button size="small" variant="outlined" disabled={!note.trim() || submitFeedback.isPending} onClick={() => submitFeedback.mutate({ id: observation.id, payload: { feedback_type: "correction", proposed_label: correctionLabel || null, proposed_severity: correctionSeverity === "" ? null : Number(correctionSeverity), proposed_zone_kind: null, proposed_geometry_geojson: {}, comment: note, evidence_ids: observation.evidence_ids } })}>Submit correction</Button>
          <Button size="small" variant="outlined" disabled={!note.trim() || submitFeedback.isPending} onClick={() => submitFeedback.mutate({ id: observation.id, payload: { feedback_type: "disagreement", proposed_label: correctionLabel || null, proposed_severity: correctionSeverity === "" ? null : Number(correctionSeverity), proposed_zone_kind: null, proposed_geometry_geojson: {}, comment: note, evidence_ids: observation.evidence_ids } })}>Submit disagreement</Button>
          <Button size="small" color="warning" disabled={createAlert.isPending} onClick={() => createAlert.mutate({ id: observation.id, payload: { title: `Agriculture observation: ${observation.observation_type}`, message: note || "Observation requires field follow-up.", severity: "warning" } })}>Create alert</Button>
        </Stack>
        {submitFeedback.isSuccess ? <Alert severity="success">Feedback submitted for an explicit reviewer decision.</Alert> : null}
        {createAlert.isSuccess ? <Alert severity="success">Linked operational alert created.</Alert> : null}
        {feedback.data?.map((item) => <Stack key={item.id} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}><Chip size="small" label={`${item.feedback_type} · ${item.status}`} /><Typography variant="caption" sx={{ flex: 1 }}>{item.comment}</Typography>{item.status === "submitted" ? <><Button size="small" onClick={() => decideFeedback.mutate({ id: item.id, payload: { status: "accepted" } })}>Accept</Button><Button size="small" color="error" onClick={() => decideFeedback.mutate({ id: item.id, payload: { status: "rejected" } })}>Reject</Button></> : null}</Stack>)}
      </Stack>
      <EvidenceFrameCarousel observationId={observation.id} />
      <Typography variant="caption" color="text.secondary">
        Evidence: {observation.evidence_ids.join(", ") || "none"}. Trend:{" "}
        {observation.trend}. Sensor/telemetry:{" "}
        {JSON.stringify(observation.sensor_values)}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Audit history: {audit.isLoading ? "loading…" : `${audit.data?.length ?? 0} recorded change(s)`}
      </Typography>
    </Stack>
  );
}
