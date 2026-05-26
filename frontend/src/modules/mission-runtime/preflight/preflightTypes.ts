export type RowStatus = "PASS" | "FAIL" | "WARN" | "SKIP" | "NOT_RUN";
export type RowOperation = "max" | "min" | "required";
export type CategoryKey = "SYSTEM_STATUS" | "DRONE_STATUS" | "MISSION";

export type PreflightCheck = {
  name: string;
  status: string;
  message?: string | null;
};

export type ParameterDefinition = {
  id: string;
  category: CategoryKey;
  label: string;
  settingKey: string;
  op: RowOperation;
  unit?: string;
  decimals?: number;
  checkNames: string[];
  telemetryPaths?: string[];
  deriveActual?: (telemetry: unknown, check: PreflightCheck | null) => unknown;
};

export type PreflightRow = {
  id: string;
  label: string;
  defaultValue: string;
  actualValue: string;
  status: RowStatus;
  statusDetail: string;
};

export type PreflightRowsByCategory = Record<CategoryKey, PreflightRow[]>;
