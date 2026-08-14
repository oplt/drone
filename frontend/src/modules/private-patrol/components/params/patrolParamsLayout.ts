import type { PrivatePatrolMissionTaskType } from "../../types";

export type ParamsTab = PrivatePatrolMissionTaskType | "event_triggered";

export const PARAM_TABS: { value: ParamsTab; label: string }[] = [
  { value: "perimeter_patrol", label: "Perimeter Patrol" },
  { value: "waypoint_patrol", label: "Waypoint Patrol" },
  { value: "grid_surveillance", label: "Grid Surveillance" },
  { value: "event_triggered", label: "Event Triggered" },
];

const fieldSx = (width: number) =>
  ({
    flex: { xs: "1 1 100%", sm: `0 0 ${width}px` },
    width: { xs: "100%", sm: width },
    minWidth: { xs: 0, sm: width },
    maxWidth: "100%",
  }) as const;

export const PARAM_FIELD_SX = {
  xxs: fieldSx(100),
  xs: fieldSx(125),
  s: fieldSx(150),
  m: fieldSx(170),
  l: fieldSx(200),
  xl: fieldSx(225),
  xxl: fieldSx(250),
} as const;

export const PARAM_FULL_ROW_SX = {
  flex: "1 1 100%",
  width: "100%",
  minWidth: 0,
} as const;

export const PARAM_GRID_SX = {
  display: "flex",
  flexWrap: "wrap",
  gap: 1.25,
  alignItems: "flex-start",
  justifyContent: "flex-start",
  "& .MuiTextField-root": {
    maxWidth: "100%",
  },
  "& .MuiInputBase-root": {
    minHeight: 58,
  },
  "& .MuiInputLabel-root": {
    maxWidth: "calc(100% - 24px)",
  },
  "& .MuiFormControlLabel-root": {
    m: 0,
    maxWidth: "100%",
    alignSelf: "center",
    "& .MuiFormControlLabel-label": {
      whiteSpace: "normal",
      lineHeight: 1.2,
    },
  },
} as const;

export const AI_TASKS_SX = {
  display: "flex",
  flexWrap: "wrap",
  gap: 1,
  alignItems: "center",
  justifyContent: "flex-start",
} as const;
