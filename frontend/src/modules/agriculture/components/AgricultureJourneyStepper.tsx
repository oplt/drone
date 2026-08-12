import { Button, Paper, Stack, Step, StepLabel, Stepper, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { agricultureJourneyStages, deriveAgricultureJourneyStage } from "../journeyState";

export function AgricultureJourneyStepper({
  flightStatus,
  analysisStatus,
  analysisRunId,
  onStartAnalysis,
  startAnalysisDisabled,
}: {
  flightStatus?: string | null;
  analysisStatus?: string | null;
  analysisRunId?: string | null;
  onStartAnalysis?: () => void;
  startAnalysisDisabled?: boolean;
}) {
  const stage = deriveAgricultureJourneyStage({ flightStatus, analysisStatus });
  return (
    <Paper component="nav" aria-label="Agriculture journey" variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1.5}>
        <Stepper activeStep={stage} alternativeLabel>
          {agricultureJourneyStages.map((label) => <Step key={label}><StepLabel>{label}</StepLabel></Step>)}
        </Stepper>
        <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ sm: "center" }} spacing={1}>
          <Typography variant="body2" color="text.secondary">
            Current stage: {agricultureJourneyStages[stage]}
          </Typography>
          {analysisRunId ? (
            <Button sx={{ minHeight: 44 }} variant="contained" component={RouterLink} to={`/dashboard/agriculture/analysis/${analysisRunId}`}>
              {stage >= 3 ? "Review findings" : "Open analysis"}
            </Button>
          ) : onStartAnalysis ? (
            <Button sx={{ minHeight: 44 }} variant="contained" onClick={onStartAnalysis} disabled={startAnalysisDisabled}>
              Start analysis
            </Button>
          ) : null}
        </Stack>
      </Stack>
    </Paper>
  );
}
