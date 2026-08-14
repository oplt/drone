import { Button, Paper, Stack, Step, StepLabel, Stepper, Typography, useMediaQuery } from "@mui/material";
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
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  return (
    <Paper component="nav" aria-label="Agriculture journey" variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1.5}>
        <Stepper
          activeStep={stage}
          alternativeLabel
          sx={{
            "& .MuiStepLabel-root .Mui-active": {
              transition: reduceMotion ? "none" : "color 160ms ease",
            },
            "& .MuiStepIcon-root": {
              transition: reduceMotion ? "none" : "transform 160ms ease, color 160ms ease",
            },
            "& .MuiStepIcon-root.Mui-active": {
              transform: reduceMotion ? "none" : "scale(1.12)",
              filter: reduceMotion ? "none" : "drop-shadow(0 0 0 2px rgba(62, 106, 225, 0.35))",
            },
            "& .MuiStepConnector-line": {
              transition: reduceMotion ? "none" : "border-color 160ms ease",
            },
          }}
        >
          {agricultureJourneyStages.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          justifyContent="space-between"
          alignItems={{ sm: "center" }}
          spacing={1}
        >
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{
              px: 1,
              py: 0.5,
              borderRadius: 1,
              bgcolor: "action.selected",
              border: "1px solid",
              borderColor: "primary.main",
              transition: reduceMotion ? "none" : "background-color 160ms ease",
            }}
          >
            Current stage: {agricultureJourneyStages[stage]}
          </Typography>
          {analysisRunId ? (
            <Button
              sx={{ minHeight: 44 }}
              variant="contained"
              component={RouterLink}
              to={`/dashboard/agriculture/analysis/${analysisRunId}`}
            >
              {stage >= 3 ? "Review findings" : "Open analysis"}
            </Button>
          ) : onStartAnalysis ? (
            <Button
              sx={{ minHeight: 44 }}
              variant="contained"
              onClick={onStartAnalysis}
              disabled={startAnalysisDisabled}
            >
              Start analysis
            </Button>
          ) : null}
        </Stack>
      </Stack>
    </Paper>
  );
}
