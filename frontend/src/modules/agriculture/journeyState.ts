export const agricultureJourneyStages = ["Capture", "Quality", "Analyze", "Review", "Act"] as const;

const activeAnalysisStatuses = new Set(["queued", "orchestrating", "waiting_inference", "running", "processing"]);
const terminalAnalysisStatuses = new Set(["completed", "succeeded", "review_ready"]);
const completedFlightStatuses = new Set(["completed", "landed", "finished", "stopped"]);

export function deriveAgricultureJourneyStage({
  flightStatus,
  analysisStatus,
  reviewComplete = false,
  actionReady = false,
}: {
  flightStatus?: string | null;
  analysisStatus?: string | null;
  reviewComplete?: boolean;
  actionReady?: boolean;
}) {
  if (actionReady || reviewComplete) return 4;
  if (analysisStatus && terminalAnalysisStatuses.has(analysisStatus)) return 3;
  if (analysisStatus && activeAnalysisStatuses.has(analysisStatus)) return 2;
  if (analysisStatus) return 2;
  if (flightStatus && completedFlightStatuses.has(flightStatus)) return 1;
  return 0;
}
