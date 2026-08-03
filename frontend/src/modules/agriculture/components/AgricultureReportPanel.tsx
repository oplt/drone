import { Alert, Button, Chip, Divider, Paper, Stack, Typography } from "@mui/material";
import { useAgricultureReport, useAgricultureReportSnapshots, useCreateAgricultureReportSnapshot } from "../hooks";

export function AgricultureReportPanel({ runId }: { runId: string }) {
  const report = useAgricultureReport(runId);
  const snapshots = useAgricultureReportSnapshots(runId);
  const createSnapshot = useCreateAgricultureReportSnapshot();
  if (report.isLoading) return <Typography variant="caption" role="status">Loading report summary…</Typography>;
  if (report.isError) return <Alert severity="warning">Report summary unavailable. Raw observations and exports remain available.</Alert>;
  if (!report.data) return null;
  const quality = report.data.quality_gate;
  return (
    <Paper component="section" aria-labelledby="agriculture-report-heading" variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Typography id="agriculture-report-heading" variant="subtitle2">Agriculture report summary</Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Chip size="small" label={`${report.data.summary.observation_count} observations`} />
          <Chip size="small" label={`${report.data.summary.confirmed_count} confirmed`} color="success" />
          <Chip size="small" label={`${report.data.summary.unreviewed_count} awaiting review`} color="warning" />
          <Chip size="small" label={`Quality ${String(quality.status ?? report.data.status)}`} />
        </Stack>
        <Typography variant="caption">Layers: {report.data.summary.layer_names.join(", ") || "none"}</Typography>
        <Divider />
        <Alert severity="info">{report.data.limitations.join(" ")}</Alert>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
          <Button size="small" variant="outlined" onClick={() => createSnapshot.mutate({ runId })} disabled={createSnapshot.isPending}>
            {createSnapshot.isPending ? "Capturing snapshot…" : "Capture reproducible snapshot"}
          </Button>
          <Typography variant="caption" color="text.secondary">
            {snapshots.data?.length ?? 0} immutable snapshot{snapshots.data?.length === 1 ? "" : "s"}
          </Typography>
        </Stack>
        {createSnapshot.isError ? <Alert severity="warning">Snapshot could not be captured. Retry when the run is available.</Alert> : null}
        {snapshots.data?.slice(0, 3).map((snapshot) => (
          <Typography key={snapshot.id} variant="caption" color="text.secondary">
            {snapshot.template_key} v{snapshot.template_version} · SHA-256 {snapshot.checksum.slice(0, 12)}… · {new Date(snapshot.created_at).toLocaleString()}
          </Typography>
        ))}
      </Stack>
    </Paper>
  );
}
