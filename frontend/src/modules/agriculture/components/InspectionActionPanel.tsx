import { Alert, Button, Chip, Stack, Typography } from "@mui/material";
import type { AgricultureInspectionAction } from "../types";

export function InspectionActionPanel({
  actions,
  loading,
  onGenerate,
  onReview,
  onAssign,
}: {
  actions: AgricultureInspectionAction[];
  loading: boolean;
  onGenerate: () => void;
  onReview: (id: string, status: "approved" | "rejected") => void;
  onAssign: (id: string) => void;
}) {
  return (
    <Stack
      component="section"
      aria-labelledby="inspection-action-heading"
      spacing={1}
    >
      <Stack
        direction={{ xs: "column", sm: "row" }}
        justifyContent="space-between"
        spacing={1}
      >
        <div>
          <Typography id="inspection-action-heading" variant="subtitle2">
            Inspection actions
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Confirmed evidence becomes a reviewable physical-inspection route.
          </Typography>
        </div>
        <Button
          size="small"
          variant="outlined"
          onClick={onGenerate}
          disabled={loading}
        >
          {loading ? "Planning…" : "Generate inspection list"}
        </Button>
      </Stack>
      {actions.length ? (
        actions.map((action) => (
          <Stack
            key={action.id}
            direction={{ xs: "column", sm: "row" }}
            spacing={1}
            alignItems={{ sm: "center" }}
          >
            <Chip
              size="small"
              label={`#${action.priority_rank} ${action.issue_type.replaceAll("_", " ")}`}
            />
            <Chip
              size="small"
              color={
                action.status === "approved"
                  ? "success"
                  : action.status === "rejected"
                    ? "error"
                    : "warning"
              }
              label={action.status}
            />
            <Typography variant="caption" sx={{ flex: 1 }}>
              Confidence {Math.round(action.confidence * 100)}% · severity{" "}
              {Math.round(action.severity * 100)}%
            </Typography>
            {action.status === "draft" ? (
              <Stack direction="row">
                <Button
                  size="small"
                  onClick={() => onReview(action.id, "approved")}
                >
                  Approve
                </Button>
                <Button
                  size="small"
                  color="error"
                  onClick={() => onReview(action.id, "rejected")}
                >
                  Reject
                </Button>
              </Stack>
            ) : null}
            <Button size="small" onClick={() => onAssign(action.id)}>Assign</Button>
          </Stack>
        ))
      ) : (
        <Alert severity="info">
          No inspection actions yet. Only confirmed observations produce
          actions.
        </Alert>
      )}
    </Stack>
  );
}
