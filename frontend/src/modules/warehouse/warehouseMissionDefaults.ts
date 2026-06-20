import type { WarehouseMissionDefaultsResponse } from "./types/missions";
import { COMPACT_FIELD_SX } from "./warehousePageSupport";

export type WarehouseMissionDefaultsKey =
  keyof WarehouseMissionDefaultsResponse;

export type WarehouseMissionDefaultsDraft = {
  [K in WarehouseMissionDefaultsKey]: string;
};

export type WarehouseMissionDefaultsRow =
  | {
      key: WarehouseMissionDefaultsKey;
      label: string;
      kind: "number";
      min?: number;
      step?: number;
      placeholder?: string;
    }
  | {
      key: WarehouseMissionDefaultsKey;
      label: string;
      kind: "select";
      options: ReadonlyArray<{ value: string; label: string }>;
    };

export const WAREHOUSE_MISSION_DEFAULT_ROWS: WarehouseMissionDefaultsRow[] = [
  {
    key: "cruise_alt",
    label: "Base Layer Altitude (m)",
    kind: "number",
    min: 0.1,
    step: 0.1,
  },
  {
    key: "corridor_spacing_m",
    label: "Corridor Spacing (m)",
    kind: "number",
    min: 0.1,
    step: 0.1,
  },
  {
    key: "aisle_axis_deg",
    label: "Aisle Axis (deg)",
    kind: "number",
    min: -180,
    step: 1,
    placeholder: "Auto",
  },
  {
    key: "clearance_m",
    label: "Clearance (m)",
    kind: "number",
    min: 0.1,
    step: 0.1,
  },
  {
    key: "perimeter_offset_m",
    label: "Perimeter Offset (m)",
    kind: "number",
    min: 0,
    step: 0.1,
  },
  {
    key: "scan_pattern",
    label: "Scan Pattern",
    kind: "select",
    options: [
      { value: "aisle_serpentine", label: "Aisle Serpentine" },
      { value: "stacked_passes", label: "Stacked Passes" },
      { value: "crosshatch", label: "Crosshatch" },
      { value: "perimeter_aisle_hybrid", label: "Perimeter + Aisles" },
    ],
  },
  {
    key: "lane_strategy",
    label: "Lane Strategy",
    kind: "select",
    options: [
      { value: "serpentine", label: "Serpentine" },
      { value: "one_way", label: "One Way" },
    ],
  },
  {
    key: "view_mode",
    label: "View Mode",
    kind: "select",
    options: [
      { value: "forward", label: "Forward" },
      { value: "left_face", label: "Left Face" },
      { value: "right_face", label: "Right Face" },
      { value: "dual_face", label: "Dual Face" },
    ],
  },
  { key: "layer_count", label: "Layer Count", kind: "number", min: 1, step: 1 },
  {
    key: "layer_spacing_m",
    label: "Layer Spacing (m)",
    kind: "number",
    min: 0,
    step: 0.1,
  },
  {
    key: "ceiling_height_m",
    label: "Ceiling Height (m)",
    kind: "number",
    min: 0.1,
    step: 0.1,
  },
  {
    key: "ceiling_margin_m",
    label: "Ceiling Margin (m)",
    kind: "number",
    min: 0,
    step: 0.1,
  },
  {
    key: "work_speed_mps",
    label: "Work Speed (m/s)",
    kind: "number",
    min: 0.1,
    step: 0.1,
  },
  {
    key: "transit_speed_mps",
    label: "Transit Speed (m/s)",
    kind: "number",
    min: 0.1,
    step: 0.1,
  },
  {
    key: "scan_pause_s",
    label: "Scan Pause (s)",
    kind: "number",
    min: 0,
    step: 0.1,
  },
  {
    key: "interpolate_steps_work_leg",
    label: "Work Leg Interpolation",
    kind: "number",
    min: 0,
    step: 1,
  },
  {
    key: "interpolate_steps_transit_leg",
    label: "Transit Leg Interpolation",
    kind: "number",
    min: 0,
    step: 1,
  },
];

export const ADVANCED_MISSION_DEFAULT_KEYS =
  new Set<WarehouseMissionDefaultsKey>([
    "aisle_axis_deg",
    "perimeter_offset_m",
    "scan_pattern",
    "lane_strategy",
    "view_mode",
    "layer_count",
    "layer_spacing_m",
    "ceiling_height_m",
    "ceiling_margin_m",
    "scan_pause_s",
    "interpolate_steps_work_leg",
    "interpolate_steps_transit_leg",
  ]);

export const toMissionDefaultColumns = (showAdvanced: boolean) => {
  const visibleRows = showAdvanced
    ? WAREHOUSE_MISSION_DEFAULT_ROWS
    : WAREHOUSE_MISSION_DEFAULT_ROWS.filter(
        (row) => !ADVANCED_MISSION_DEFAULT_KEYS.has(row.key),
      );
  const columnCount = showAdvanced ? 4 : 2;
  const rowsPerColumn = Math.ceil(visibleRows.length / columnCount);
  return Array.from({ length: columnCount }, (_, index) =>
    visibleRows.slice(index * rowsPerColumn, (index + 1) * rowsPerColumn),
  ).filter((column) => column.length > 0);
};

export const MISSION_DEFAULT_VALUE_SX = {
  ...COMPACT_FIELD_SX,
  width: "100%",
  maxWidth: 96,
  ml: "auto",
  "& .MuiFilledInput-root": {
    ...COMPACT_FIELD_SX["& .MuiFilledInput-root"],
    fontSize: "0.68rem",
  },
  "& .MuiFilledInput-input": {
    px: 0.5,
    py: 0.45,
    pt: 0.95,
    fontSize: "0.68rem",
    lineHeight: 1.2,
  },
  "& .MuiSelect-select": {
    fontSize: "0.68rem",
    py: 0.45,
    pt: 0.95,
    minHeight: "1.25rem",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
} as const;

export const toWarehouseMissionDefaultsDraft = (
  defaults: WarehouseMissionDefaultsResponse,
): WarehouseMissionDefaultsDraft => ({
  cruise_alt: String(defaults.cruise_alt),
  corridor_spacing_m: String(defaults.corridor_spacing_m),
  aisle_axis_deg:
    defaults.aisle_axis_deg == null ? "" : String(defaults.aisle_axis_deg),
  clearance_m: String(defaults.clearance_m),
  perimeter_offset_m: String(defaults.perimeter_offset_m),
  scan_pattern: defaults.scan_pattern,
  lane_strategy: defaults.lane_strategy,
  view_mode: defaults.view_mode,
  layer_count: String(defaults.layer_count),
  layer_spacing_m: String(defaults.layer_spacing_m),
  ceiling_height_m: String(defaults.ceiling_height_m),
  ceiling_margin_m: String(defaults.ceiling_margin_m),
  work_speed_mps: String(defaults.work_speed_mps),
  transit_speed_mps: String(defaults.transit_speed_mps),
  scan_pause_s: String(defaults.scan_pause_s),
  interpolate_steps_work_leg: String(defaults.interpolate_steps_work_leg),
  interpolate_steps_transit_leg: String(defaults.interpolate_steps_transit_leg),
});

export const parseRequiredNumber = (
  label: string,
  raw: string,
  integer = false,
): number => {
  const trimmed = raw.trim();
  if (!trimmed) {
    throw new Error(`${label} is required.`);
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be a valid number.`);
  }
  if (integer && !Number.isInteger(parsed)) {
    throw new Error(`${label} must be a whole number.`);
  }
  return parsed;
};

export const parseOptionalNumber = (
  label: string,
  raw: string,
): number | null => {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const parsed = Number.parseFloat(trimmed);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be a valid number.`);
  }
  return parsed;
};

export const toWarehouseMissionDefaultsPayload = (
  draft: WarehouseMissionDefaultsDraft,
): WarehouseMissionDefaultsResponse => ({
  cruise_alt: parseRequiredNumber("Cruise altitude", draft.cruise_alt),
  corridor_spacing_m: parseRequiredNumber(
    "Corridor spacing",
    draft.corridor_spacing_m,
  ),
  aisle_axis_deg: parseOptionalNumber("Aisle axis", draft.aisle_axis_deg),
  clearance_m: parseRequiredNumber("Clearance", draft.clearance_m),
  perimeter_offset_m: parseRequiredNumber(
    "Perimeter offset",
    draft.perimeter_offset_m,
  ),
  scan_pattern:
    draft.scan_pattern as WarehouseMissionDefaultsResponse["scan_pattern"],
  lane_strategy:
    draft.lane_strategy as WarehouseMissionDefaultsResponse["lane_strategy"],
  view_mode: draft.view_mode as WarehouseMissionDefaultsResponse["view_mode"],
  layer_count: parseRequiredNumber("Layer count", draft.layer_count, true),
  layer_spacing_m: parseRequiredNumber("Layer spacing", draft.layer_spacing_m),
  ceiling_height_m: parseRequiredNumber(
    "Ceiling height",
    draft.ceiling_height_m,
  ),
  ceiling_margin_m: parseRequiredNumber(
    "Ceiling margin",
    draft.ceiling_margin_m,
  ),
  work_speed_mps: parseRequiredNumber("Work speed", draft.work_speed_mps),
  transit_speed_mps: parseRequiredNumber(
    "Transit speed",
    draft.transit_speed_mps,
  ),
  scan_pause_s: parseRequiredNumber("Scan pause", draft.scan_pause_s),
  interpolate_steps_work_leg: parseRequiredNumber(
    "Work leg interpolation",
    draft.interpolate_steps_work_leg,
    true,
  ),
  interpolate_steps_transit_leg: parseRequiredNumber(
    "Transit leg interpolation",
    draft.interpolate_steps_transit_leg,
    true,
  ),
});
