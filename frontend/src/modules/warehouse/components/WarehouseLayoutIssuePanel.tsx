import { Alert, List, ListItem, ListItemText, Typography } from "@mui/material";
import type { LayoutIssue } from "../api/warehouseLayoutApi";

export function WarehouseLayoutIssuePanel({
  issues,
}: {
  issues: LayoutIssue[];
}) {
  if (issues.length === 0) {
    return <Alert severity="success">No layout issues detected.</Alert>;
  }
  return (
    <Alert
      severity={
        issues.some((issue) => issue.severity === "error") ? "error" : "warning"
      }
    >
      <Typography variant="subtitle2">
        Validation issues ({issues.length})
      </Typography>
      <List dense disablePadding>
        {issues.map((issue, index) => (
          <ListItem key={`${issue.code}:${issue.path}:${index}`} disableGutters>
            <ListItemText
              primary={issue.message}
              secondary={`${issue.code} · ${issue.path}`}
            />
          </ListItem>
        ))}
      </List>
    </Alert>
  );
}
