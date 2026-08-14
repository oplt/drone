import type { SaveIndicatorState } from "./SaveIndicator";

export function labelingSaveToIndicator(
  saveState: "saved" | "saving" | "failed",
): SaveIndicatorState {
  if (saveState === "saving") return "saving";
  if (saveState === "failed") return "error";
  return "saved";
}
