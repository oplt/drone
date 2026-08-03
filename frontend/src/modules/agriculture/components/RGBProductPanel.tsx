import { Alert, Chip, Paper, Stack, Typography } from "@mui/material";

type RGBProduct = {
  label?: string;
  claim?: string;
  status?: string;
  claim_status?: string;
  confidence?: number;
  model_version?: string;
  model_gate?: string;
  reason?: string | null;
  limitations?: string[];
  validated_model_available?: boolean;
  model_evidence?: { reason?: string; report_id?: string | null; artifact_digest?: string | null; dataset_key?: string | null };
};

export function RGBProductPanel({ products }: { products: Record<string, unknown> }) {
  const entries = Object.entries(products).filter(([, value]) => value && typeof value === "object") as Array<[string, RGBProduct]>;
  if (!entries.length) return null;
  return (
    <Paper component="section" aria-labelledby="rgb-products-heading" variant="outlined" sx={{ p: 1.25 }}>
      <Stack spacing={1}>
        <Typography id="rgb-products-heading" variant="subtitle2">RGB analysis products</Typography>
        <Alert severity="info">RGB outputs are candidate signatures for review. They are not confirmed disease, nutrient, moisture, yield, or treatment claims.</Alert>
        {entries.map(([name, product]) => (
          <Stack key={name} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
            <Typography sx={{ minWidth: 170 }} variant="body2">{product.label ?? name.replaceAll("_", " ")}</Typography>
            <Chip size="small" label={product.status ?? "unknown"} color={product.status === "candidate" ? "warning" : product.status === "blocked_quality" ? "error" : "default"} />
            <Chip size="small" variant="outlined" label={`Confidence ${Math.round(Number(product.confidence ?? 0) * 100)}%`} />
            <Typography variant="caption" color="text.secondary">{product.claim ?? "candidate output"} · {product.model_gate ?? "candidate_only"} · {product.model_version ?? "unknown model"}</Typography>
            {product.model_gate !== "publishable" ? <Typography variant="caption" color="warning.main">Release gate: candidate-only{product.model_evidence?.reason ? ` · ${product.model_evidence.reason}` : " · validated artifact/evaluation evidence required"}</Typography> : null}
            {product.reason ? <Typography variant="caption" color="text.secondary">{product.reason}</Typography> : null}
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}
