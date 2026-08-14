import {
  Alert,
  Button,
  Chip,
  Divider,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import {
  useAgricultureExports,
  useAgricultureInspectionActions,
  useAgriculturePrescriptions,
  useApproveAgricultureInspectionAction,
  useAssignAgricultureInspectionAction,
  useApproveAgriculturePrescription,
  useCreateAgricultureExport,
  useCreateAgricultureInspectionPlan,
  useCreateAgriculturePrescription,
  useGetAgricultureExportDownload,
  useUpdateAgricultureInspectionRoute,
} from "../hooks";
import { ExportApprovalDialog } from "./ExportApprovalDialog";
import { InspectionActionPanel } from "./InspectionActionPanel";
import { AssignReviewerDialog } from "./AssignReviewerDialog";
import { AgricultureInterventionZoneWorkspace } from "./AgricultureInterventionZoneWorkspace";

export function AgricultureActionExportPanel({ runId }: { runId: string }) {
  const actions = useAgricultureInspectionActions(runId);
  const prescriptions = useAgriculturePrescriptions(runId);
  const exports = useAgricultureExports(runId);
  const plan = useCreateAgricultureInspectionPlan();
  const approveAction = useApproveAgricultureInspectionAction();
  const assignAction = useAssignAgricultureInspectionAction();
  const updateRoute = useUpdateAgricultureInspectionRoute();
  const createPrescription = useCreateAgriculturePrescription();
  const approvePrescription = useApproveAgriculturePrescription();
  const createExport = useCreateAgricultureExport();
  const download = useGetAgricultureExportDownload();
  const [ruleId, setRuleId] = useState("");
  const [link, setLink] = useState<string | null>(null);
  const [assigningActionId, setAssigningActionId] = useState<string | null>(null);
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1.25}>
        <Typography variant="subtitle2">
          Actions, prescriptions and exports
        </Typography>
        <AgricultureInterventionZoneWorkspace runId={runId} />
        <Divider />
        <InspectionActionPanel
          actions={actions.data ?? []}
          loading={plan.isPending || updateRoute.isPending}
          onGenerate={() => plan.mutate({ runId, payload: {} })}
          onReview={(id, status) => approveAction.mutate({ id, runId, status })}
          onAssign={(id) => setAssigningActionId(id)}
          onRouteChange={(payload) => updateRoute.mutate({ runId, payload })}
        />
        <AssignReviewerDialog
          open={Boolean(assigningActionId)}
          pending={assignAction.isPending}
          onClose={() => setAssigningActionId(null)}
          onAssign={(userId) => {
            if (!assigningActionId) return;
            assignAction.mutate({ id: assigningActionId, runId, payload: { assigned_to_user_id: userId, reason: "Signed-in reviewer assignment" } }, { onSuccess: () => setAssigningActionId(null) });
          }}
        />
        {plan.error ? (
          <Alert severity="warning">
            Inspection planning blocked or failed. Confirm observations and
            check field/battery constraints.
          </Alert>
        ) : null}
        <Divider />
        <Typography variant="caption" color="text.secondary">
          Prescription draft
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField
            size="small"
            label="Approved rule id"
            value={ruleId}
            onChange={(event) => setRuleId(event.target.value)}
            inputProps={{ "aria-label": "Approved agronomy rule id" }}
          />
          <Button
            size="small"
            variant="outlined"
            disabled={!ruleId.trim() || createPrescription.isPending}
            onClick={() =>
              createPrescription.mutate({ runId, ruleId: ruleId.trim() })
            }
          >
            Build draft
          </Button>
        </Stack>
        {prescriptions.data?.map((draft) => (
          <Stack key={draft.id} spacing={0.5}>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              <Chip
                size="small"
                label={draft.status}
                color={
                  draft.status === "approved"
                    ? "success"
                    : draft.status === "blocked"
                      ? "error"
                      : "warning"
                }
              />
              <Chip
                size="small"
                variant="outlined"
                label={`Zones ${draft.zones.length}`}
              />
              <Chip
                size="small"
                variant="outlined"
                label={`Confidence ${Math.round(draft.confidence * 100)}%`}
              />
              {draft.status === "draft" ? (
                <>
                  <Button
                    size="small"
                    color="success"
                    onClick={() =>
                      approvePrescription.mutate({
                        id: draft.id,
                        runId,
                        status: "approved",
                      })
                    }
                  >
                    Approve draft
                  </Button>
                  <Button
                    size="small"
                    color="error"
                    onClick={() =>
                      approvePrescription.mutate({
                        id: draft.id,
                        runId,
                        status: "rejected",
                      })
                    }
                  >
                    Reject draft
                  </Button>
                </>
              ) : null}
            </Stack>
            <Typography variant="caption">
              Assumptions: {draft.assumptions.join("; ")} · provenance:{" "}
              {JSON.stringify(draft.rule_provenance)}
            </Typography>
          </Stack>
        ))}
        <Divider />
        <ExportApprovalDialog
          exports={exports.data ?? []}
          pending={createExport.isPending}
          error={Boolean(createExport.error)}
          onGenerate={(artifactKind, format) =>
            createExport.mutate({
              runId,
              payload: { artifact_kind: artifactKind, format },
            })
          }
          onDownload={(id) =>
            download.mutate(id, {
              onSuccess: (result) => setLink(result.download_url),
            })
          }
        />
        {link ? (
          <Alert severity="success">
            Signed link ready:{" "}
            <a href={link} target="_blank" rel="noreferrer">
              download artifact
            </a>
          </Alert>
        ) : null}
      </Stack>
    </Paper>
  );
}
