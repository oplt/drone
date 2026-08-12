import { Alert, Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useAgricultureAlertActions, useAgricultureAlerts, useAssignAgricultureAlert } from "../alerts";
import { AssignReviewerDialog } from "./AssignReviewerDialog";

export function AgricultureAlertCenter() {
  const alerts = useAgricultureAlerts();
  const actions = useAgricultureAlertActions();
  const assign = useAssignAgricultureAlert();
  const [assigningId, setAssigningId] = useState<number | null>(null);
  if (alerts.isLoading) return <Typography variant="caption" role="status">Loading operational alerts…</Typography>;
  if (alerts.isError) return <Alert severity="warning">Operational alert center unavailable. Flight safety state remains authoritative.</Alert>;
  return (
    <Paper component="section" aria-labelledby="agriculture-alert-center-heading" variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Typography id="agriculture-alert-center-heading" variant="subtitle2">Operational alerts</Typography>
        {!alerts.data?.items.length ? <Alert severity="success">No active agriculture alerts.</Alert> : null}
        {alerts.data?.items.map((item) => (
          <Stack key={item.id} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
            <Chip size="small" label={item.severity} color={item.severity === "critical" ? "error" : "warning"} />
            <Stack sx={{ flex: 1 }}>
              <Typography variant="body2">{item.title}</Typography>
              <Typography variant="caption" color="text.secondary">{item.message} · {item.occurrences} occurrence(s)</Typography>
              <Typography variant="caption" color="text.secondary">{item.assigned_to_user_id ? `Assigned to user ${item.assigned_to_user_id}` : "Unassigned"}{item.due_at ? ` · due ${new Date(item.due_at).toLocaleString()}` : ""}</Typography>
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
