import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { PageSection } from "../../../shared/layout/PageLayout";

type DashboardAlertsPanelProps = {
  items: string[];
};

export default function DashboardAlertsPanel({
  items,
}: DashboardAlertsPanelProps) {
  const visibleItems = items.slice(0, 3);
  const hiddenCount = Math.max(0, items.length - visibleItems.length);

  return (
    <PageSection
      title="Alerts"
      description="Only current watch items. Hover for full text."
      sx={{ height: "100%", p: 2 }}
    >
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No critical alerts.
        </Typography>
      ) : (
        <Stack spacing={1}>
          {visibleItems.map((item) => (
            <Tooltip key={item} title={item} arrow>
              <Alert
                severity="warning"
                sx={{
                  py: 0.5,
                  "& .MuiAlert-message": {
                    width: "100%",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  },
                }}
              >
                {item}
              </Alert>
            </Tooltip>
          ))}
          {hiddenCount > 0 ? (
            <Tooltip title={items.slice(3).join("\n")} arrow>
              <Chip size="small" label={`+${hiddenCount} more`} />
            </Tooltip>
          ) : null}
        </Stack>
      )}
    </PageSection>
  );
}
