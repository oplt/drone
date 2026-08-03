import { Alert, Button, Chip, CircularProgress, Paper, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useAgricultureModelGovernanceActions, useAgricultureModelQualityReports, useAgricultureModelReleaseGate, useAgricultureModels } from "../hooks";

export function AgricultureModelRegistryPanel() {
  const models = useAgricultureModels();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const reports = useAgricultureModelQualityReports(selectedId);
  const gate = useAgricultureModelReleaseGate(selectedId);
  const actions = useAgricultureModelGovernanceActions();
  const selected = models.data?.find((model) => model.id === selectedId);
  if (models.isLoading) return <Stack role="status"><CircularProgress size={18} /></Stack>;
  if (models.isError) return <Alert severity="warning">Model registry unavailable; model provenance remains hidden until it can be verified.</Alert>;
  return (
    <Paper component="section" aria-labelledby="model-registry-heading" variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <div><Typography id="model-registry-heading" variant="subtitle2">Model and evaluation registry</Typography><Typography variant="caption" color="text.secondary">Only tenant-scoped models and their evaluation evidence are shown. Publishing is controlled by server-side validation gates.</Typography></div>
        {!models.data?.length ? <Alert severity="info">No registered crop model artifacts are available.</Alert> : models.data.map((model) => (
          <Stack key={model.id} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }} sx={{ p: 1, border: 1, borderColor: "divider", borderRadius: 1 }}>
            <Stack sx={{ flex: 1 }}><Typography>{model.task} · {model.version}</Typography><Typography variant="caption" color="text.secondary">Artifact: {model.artifact_uri ?? "missing"} · dataset: {model.dataset_key ?? "missing"}</Typography></Stack>
            <Chip size="small" label={model.status} color={model.status === "deployed" ? "success" : model.status === "validated" ? "info" : "warning"} />
            <Chip size="small" variant="outlined" label={model.dataset_key ?? "dataset unspecified"} />
            <button type="button" onClick={() => setSelectedId(model.id)} aria-label={`Show evaluations for ${model.task} ${model.version}`}>Evaluations</button>
          </Stack>
        ))}
        {selectedId ? <Stack role="region" aria-label="Selected model governance" spacing={0.75}>
          <Typography variant="caption">Evaluation and release gate</Typography>
          {gate.isLoading ? <CircularProgress size={16} /> : gate.data ? <>
            <Chip size="small" label={gate.data.publishable ? "Publish gate passed" : "Publish blocked"} color={gate.data.publishable ? "success" : "warning"} />
            {!gate.data.publishable ? <Typography variant="caption" color="warning.main">{gate.data.evidence_gate.failures.join("; ") || "Evaluation or evidence requirements are incomplete."}</Typography> : null}
            <Typography variant="caption" color="text.secondary">Artifact digest: {gate.data.evidence_gate.artifact_digest ?? "missing"} · evaluation checksum: {gate.data.evaluation_checksum ?? "missing"}</Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button size="small" variant="outlined" disabled={!selected || actions.shadow.isPending} onClick={() => { if (selected) { const metrics = Object.fromEntries(Object.entries(selected.metrics).filter((entry): entry is [string, number] => typeof entry[1] === "number")); actions.shadow.mutate({ id: selected.id, payload: { metrics, sensor_type: "rgb" } }); } }}>Run shadow evaluation</Button>
              <Button size="small" color="success" disabled={!gate.data.publishable || selected?.status !== "validated" || actions.publish.isPending} onClick={() => selected && actions.publish.mutate(selected.id)}>Publish validated model</Button>
              {selected?.status === "deployed" && models.data?.find((candidate) => candidate.task === selected.task && candidate.status === "retired") ? <Button size="small" color="warning" disabled={actions.rollback.isPending} onClick={() => { const target = models.data?.find((candidate) => candidate.task === selected.task && candidate.status === "retired"); if (target) actions.rollback.mutate({ id: selected.id, targetId: target.id }); }}>Rollback to retired model</Button> : null}
            </Stack>
          </> : null}
          {reports.isLoading ? <CircularProgress size={16} /> : reports.data?.length ? reports.data.map((report) => <Typography key={String(report.id)} variant="caption">{String(report.scope)} · checksum {String(report.evaluation_checksum ?? "unavailable")} · drift {JSON.stringify(report.drift ?? {})}</Typography>) : <Typography variant="caption">No evaluation reports recorded.</Typography>}
          {actions.publish.isError || actions.shadow.isError || actions.rollback.isError ? <Alert severity="error">Governance action was rejected by the server gate or permissions policy.</Alert> : null}
        </Stack> : null}
      </Stack>
    </Paper>
  );
}
