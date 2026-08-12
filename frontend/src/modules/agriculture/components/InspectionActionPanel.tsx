import { Alert, Button, Chip, Stack, Typography } from "@mui/material";
import type { AgricultureInspectionAction } from "../types";

export function InspectionActionPanel({
  actions,
  loading,
  onGenerate,
  onReview,
  onAssign,
  onRouteChange,
}: {
  actions: AgricultureInspectionAction[];
  loading: boolean;
  onGenerate: () => void;
  onReview: (id: string, status: "approved" | "rejected") => void;
  onAssign: (id: string) => void;
  onRouteChange?: (payload: {
    ordered_action_ids: string[];
    removed_action_ids?: string[];
    reason?: string;
  }) => void;
}) {
  const active = actions
    .filter((action) => action.status !== "rejected")
    .slice()
    .sort((a, b) => a.priority_rank - b.priority_rank);

  const move = (actionId: string, direction: -1 | 1) => {
    if (!onRouteChange) return;
    const index = active.findIndex((action) => action.id === actionId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= active.length) return;
    const next = active.slice();
    const [item] = next.splice(index, 1);
    next.splice(target, 0, item);
    onRouteChange({
      ordered_action_ids: next.map((action) => action.id),
      reason: direction < 0 ? "Moved up in inspection route" : "Moved down in inspection route",
    });
  };

  const removeFromRoute = (actionId: string) => {
    if (!onRouteChange) return;
    onRouteChange({
      ordered_action_ids: active.filter((action) => action.id !== actionId).map((action) => action.id),
      removed_action_ids: [actionId],
      reason: "Removed from inspection route",
    });
  };

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
      {active.length ? (
        active.map((action, index) => (
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
            {onRouteChange ? (
              <Stack direction="row">
                <Button size="small" disabled={index === 0} onClick={() => move(action.id, -1)}>
                  Move up
                </Button>
                <Button
                  size="small"
                  disabled={index === active.length - 1}
                  onClick={() => move(action.id, 1)}
                >
                  Move down
                </Button>
                <Button size="small" color="warning" onClick={() => removeFromRoute(action.id)}>
                  Remove from route
                </Button>
              </Stack>
            ) : null}
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
