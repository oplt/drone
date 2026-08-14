import * as yup from "yup";

/** Agriculture planner numeric safety bounds (altitude + photogrammetry overlap). */
export const agriculturePlannerSchema = yup.object({
  altitude: yup
    .number()
    .typeError("Altitude is required")
    .min(5, "Altitude must be at least 5 m")
    .max(120, "Altitude must be at most 120 m")
    .required("Altitude is required"),
  rowSpacing: yup
    .number()
    .typeError("Row spacing is required")
    .min(1, "Row spacing must be at least 1 m")
    .max(200, "Row spacing must be at most 200 m")
    .required("Row spacing is required"),
  gridAngle: yup
    .number()
    .typeError("Grid angle is required")
    .min(0, "Grid angle must be 0–179°")
    .max(179, "Grid angle must be 0–179°")
    .required("Grid angle is required"),
  safetyInset: yup
    .number()
    .typeError("Inset is required")
    .min(0, "Inset cannot be negative")
    .max(100, "Inset must be at most 100 m")
    .required("Inset is required"),
  front_overlap_pct: yup
    .number()
    .typeError("Front overlap is required")
    .min(50, "Front overlap must be 50–95%")
    .max(95, "Front overlap must be 50–95%")
    .required("Front overlap is required"),
  side_overlap_pct: yup
    .number()
    .typeError("Side overlap is required")
    .min(40, "Side overlap must be 40–95%")
    .max(95, "Side overlap must be 40–95%")
    .required("Side overlap is required"),
});

export type AgriculturePlannerFormValues = yup.InferType<typeof agriculturePlannerSchema>;

/** 5-field cron (minute hour dom month dow). Empty string allowed (manual-only). */
export function isValidCronExpression(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  const parts = trimmed.split(/\s+/);
  if (parts.length !== 5) return false;
  const fieldOk = (part: string, min: number, max: number): boolean => {
    if (part === "*") return true;
    if (/^\*\/\d+$/.test(part)) {
      const step = Number(part.slice(2));
      return Number.isFinite(step) && step > 0;
    }
    if (/^\d+(-\d+)?(\/\d+)?$/.test(part)) {
      const [range, step] = part.split("/");
      const [lo, hi] = range.split("-").map(Number);
      if (!Number.isFinite(lo) || lo < min || lo > max) return false;
      if (hi !== undefined && (!Number.isFinite(hi) || hi < lo || hi > max)) return false;
      if (step !== undefined) {
        const s = Number(step);
        if (!Number.isFinite(s) || s <= 0) return false;
      }
      return true;
    }
    if (part.includes(",")) {
      return part.split(",").every((item) => fieldOk(item, min, max));
    }
    return false;
  };
  const [minute, hour, dom, month, dow] = parts;
  return (
    fieldOk(minute, 0, 59) &&
    fieldOk(hour, 0, 23) &&
    fieldOk(dom, 1, 31) &&
    fieldOk(month, 1, 12) &&
    fieldOk(dow, 0, 7)
  );
}
