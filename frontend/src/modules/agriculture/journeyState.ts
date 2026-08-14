import {
  isAgricultureRunActive,
  isAgricultureRunTerminal,
} from "./workflows/analysisLifecycle";

export const agricultureJourneyStages = ["Capture", "Quality", "Analyze", "Review", "Act"] as const;

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
  if (analysisStatus && isAgricultureRunTerminal(analysisStatus)) return 3;
  if (analysisStatus && isAgricultureRunActive(analysisStatus)) return 2;
  if (analysisStatus) return 2;
  if (flightStatus && completedFlightStatuses.has(flightStatus)) return 1;
  return 0;
}
