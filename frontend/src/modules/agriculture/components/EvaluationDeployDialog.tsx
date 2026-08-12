import { Check } from "@mui/icons-material";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from "@mui/material";
import { metricSummary, percent } from "../evaluationDisplay";
import type { ModelEvaluation, VisionModelVersion } from "../visionTypes";

export function EvaluationDeployDialog({
  open,
  version,
  evaluation,
  currentProduction,
  pending,
  close,
  confirm,
}: {
  open: boolean;
  version: VisionModelVersion;
  evaluation: ModelEvaluation;
  currentProduction?: VisionModelVersion;
  pending: boolean;
  close: () => void;
  confirm: () => void;
}) {
  return (
    <Dialog open={open} onClose={close} maxWidth="sm" fullWidth>
      <DialogTitle>Deploy {version.name} v{version.version}?</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1}>
          {currentProduction ? (
            <Alert severity="warning">
              This replaces production v{currentProduction.version}. Its weights and metrics remain available.
            </Alert>
          ) : (
            <Alert severity="info">This will become the first production version.</Alert>
          )}
          <Typography>Candidate mAP50: <strong>{percent(evaluation.summary.map50)}</strong></Typography>
          {currentProduction ? (
            <Typography>
              Current production mAP50: <strong>{percent(metricSummary(currentProduction).map50)}</strong>
            </Typography>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button variant="contained" startIcon={<Check />} disabled={pending} onClick={confirm}>
          Confirm deployment
        </Button>
      </DialogActions>
    </Dialog>
  );
}
