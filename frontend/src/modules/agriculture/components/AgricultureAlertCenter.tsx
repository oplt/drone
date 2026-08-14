import { Alert, Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useAgricultureAlertActions, useAgricultureAlerts, useAssignAgricultureAlert } from "../alerts";
import { AssignReviewerDialog } from "./AssignReviewerDialog";

export function AgricultureAlertCenter() {
  const alerts = useAgricultureAlerts();
  const actions = useAgricultureAlertActions();
  const assign = useAssignAgricultureAlert();
  const [assigningId, setAssigningId] = useState<number | null>(null);

  const severityChip = (severity: string) => {
    const n = severity.toLowerCase();
    if (n === "critical" || n === "error") {
      return <Chip size="small" label={severity} color="error" />;
    }
    if (n === "high" || n === "warning") {
      return <Chip size="small" label={severity} color="warning" />;
    }
    if (n === "medium") {
      return <Chip size="small" label={severity} color="info" variant="outlined" />;
    }
    return <Chip size="small" label={severity} color="default" variant="outlined" />;
  };

  if (alerts.isLoading) return <Typography variant="caption" role="status">Loading operational alerts…</Typography>;
  if (alerts.isError) return <Alert severity="warning">Operational alert center unavailable. Flight safety state remains authoritative.</Alert>;
  return (
    <Paper component="section" aria-labelledby="agriculture-alert-center-heading" variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography id="agriculture-alert-center-heading" variant="subtitle2">Operational alerts</Typography>
          <Chip size="small" label="critical" color="error" />
          <Chip size="small" label="warning" color="warning" />
          <Chip size="small" label="medium" color="info" variant="outlined" />
          <Chip size="small" label="low" color="default" variant="outlined" />
        </Stack>
        {!alerts.data?.items.length ? <Alert severity="success">No active agriculture alerts.</Alert> : null}
        {alerts.data?.items.map((item) => (
          <Stack key={item.id} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
            {severityChip(item.severity)}
            <Stack sx={{ flex: 1 }}>
              <Typography variant="body2">{item.title}</Typography>
              <Typography variant="caption" color="text.secondary">{item.message} · {item.occurrences} occurrence(s)</Typography>
              <Typography variant="caption" color="text.secondary">{item.assigned_to_user_id ? `Assigned to user ${item.assigned_to_user_id}` : "Unassigned"}{item.due_at ? ` · due ${new Date(item.due_at).toLocaleDateString()}` : ""}</Typography>
            </Stack>
            {!item.assigned_to_user_id ? <Button size="small" onClick={() => setAssigningId(item.id)}>Assign</Button> : null}
            <Button size="small" onClick={() => actions.mutate({ id: item.id, action: "ack" })} disabled={actions.isPending}>Acknowledge</Button>
            <Button size="small" color="success" onClick={() => actions.mutate({ id: item.id, action: "resolve" })} disabled={actions.isPending}>Resolve</Button>
          </Stack>
        ))}
        <AssignReviewerDialog
          open={Boolean(assigningId)}
          pending={assign.isPending}
          onClose={() => setAssigningId(null)}
          onAssign={(userId) => {
            if (!assigningId) return;
            assign.mutate({ id: assigningId, assigned_to_user_id: userId }, { onSuccess: () => setAssigningId(null) });
          }}
        />
      </Stack>
    </Paper>
  );
}
