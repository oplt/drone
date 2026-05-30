export const readNestedValue = (value: unknown, path: string[]): unknown => {
  let current: unknown = value;
  for (const segment of path) {
    if (
      current == null ||
      typeof current !== "object" ||
      !(segment in (current as Record<string, unknown>))
    ) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
};

export const firstFiniteNumber = (...values: unknown[]): number | null => {
  for (const value of values) {
    const num = Number(value);
    if (Number.isFinite(num)) return num;
  }
  return null;
};

export function telemetryBatteryPercent(telemetry: unknown): number | null {
  return firstFiniteNumber(
    readNestedValue(telemetry, ["battery", "remaining_percent"]),
    readNestedValue(telemetry, ["battery", "remaining"]),
    readNestedValue(telemetry, ["status", "battery_remaining"]),
    readNestedValue(telemetry, ["battery_remaining"]),
  );
}

export function telemetryGpsFixType(telemetry: unknown): number | null {
  return firstFiniteNumber(
    readNestedValue(telemetry, ["gps", "fix_type"]),
    readNestedValue(telemetry, ["status", "gps_fix_type"]),
    readNestedValue(telemetry, ["gps_fix_type"]),
  );
}

export function telemetryHeartbeatReceived(telemetry: unknown): boolean {
  return readNestedValue(telemetry, ["heartbeat", "last_received"]) != null;
}

export function telemetryBoolean(telemetry: unknown, path: string[]): boolean | null {
  const value = readNestedValue(telemetry, path);
  return value == null ? null : Boolean(value);
}
