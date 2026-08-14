#!/usr/bin/env node

/**
 * Telemetry UI update budget (complements check_bundle_budgets.mjs).
 *
 * Threshold: TELEMETRY_UI_NOTIFY_MIN_MS = 100 → ~10 Hz React fan-out under
 * high-rate MAVLink/sensor storms (see useTelemetryStream.ts scheduleNotify).
 *
 * Run:
 *   npm run check:telemetry-ui-budget
 *   node scripts/check_telemetry_ui_budget.mjs
 *
 * Optional: TELEMETRY_UI_BUDGET_MS=100 to override expected constant.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const EXPECTED_MS = Number(process.env.TELEMETRY_UI_BUDGET_MS ?? "100");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const streamPath = resolve(
  root,
  "src/modules/mission-runtime/hooks/useTelemetryStream.ts",
);

const source = readFileSync(streamPath, "utf8");
const match = source.match(
  /export const TELEMETRY_UI_NOTIFY_MIN_MS\s*=\s*(\d+)/,
);
if (!match) {
  console.error(
    "Missing export TELEMETRY_UI_NOTIFY_MIN_MS in useTelemetryStream.ts",
  );
  process.exitCode = 1;
} else {
  const actual = Number(match[1]);
  if (actual !== EXPECTED_MS) {
    console.error(
      `Telemetry UI budget mismatch: expected ${EXPECTED_MS}ms, found ${actual}ms`,
    );
    process.exitCode = 1;
  } else {
    console.log(
      `Telemetry UI budget OK: coalesce ≥ ${actual}ms (~${Math.round(1000 / actual)} Hz max notify).`,
    );
  }
}
