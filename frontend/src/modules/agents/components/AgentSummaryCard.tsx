import { Alert, Box, Chip, Stack, Typography } from "@mui/material";
import type { AgentResult } from "../api/agentsApi";

type Props = {
  title?: string;
  result: AgentResult | null;
  error?: string | null;
  loading?: boolean;
};

export function AgentSummaryCard({
  title = "AI summary",
  result,
  error,
  loading = false,
}: Props) {
  if (loading) {
    return (
      <Alert severity="info" sx={{ mt: 1 }}>
        Generating {title.toLowerCase()}…
      </Alert>
    );
  }

  if (error) {
    return (
      <Alert severity="warning" sx={{ mt: 1 }}>
        {error}
      </Alert>
    );
  }

  if (!result?.text) {
    return null;
  }

  const structured = result.structured ?? {};
  const operatorMessage =
    typeof structured.operator_message === "string"
      ? structured.operator_message
      : result.text;

  return (
    <Box sx={{ mt: 1, p: 1.5, borderRadius: 1, bgcolor: "action.hover" }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
        <Typography variant="subtitle2">{title}</Typography>
        {result.risk_level ? (
          <Chip size="small" label={result.risk_level} color="warning" variant="outlined" />
        ) : null}
        {result.requires_human_approval ? (
          <Chip size="small" label="Review required" color="error" variant="outlined" />
        ) : null}
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {operatorMessage}
      </Typography>
    </Box>
  );
}
