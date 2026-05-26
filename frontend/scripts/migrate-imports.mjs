#!/usr/bin/env node
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const SRC = join(import.meta.dirname, "../src");

const REPLACEMENTS = [
  [/from ["'](\.\.\/)+hooks\/useErrors["']/g, 'from "$1shared/hooks/useErrors"'],
  [/from ["'](\.\.\/)+hooks\/useInterval["']/g, 'from "$1shared/hooks/useInterval"'],
  [/from ["'](\.\.\/)+hooks\/useMissionWebsocketRuntime["']/g, 'from "$1modules/mission-runtime"'],
  [/from ["'](\.\.\/)+hooks\/useDroneCenter["']/g, 'from "$1modules/maps"'],
  [/from ["'](\.\.\/)+hooks\/useDroneMapFollow["']/g, 'from "$1modules/maps"'],
  [/from ["'](\.\.\/)+hooks\/useAutoStartVideo["']/g, 'from "$1modules/mission-runtime"'],
  [/from ["'](\.\.\/)+hooks\/useMissionCommandMetrics["']/g, 'from "$1modules/mission-runtime"'],
  [/from ["'](\.\.\/)+hooks\/useMissionStatusPolling["']/g, 'from "$1modules/mission-runtime"'],
  [/from ["'](\.\.\/)+hooks\/useAnalyticsOverview["']/g, 'from "$1modules/dashboard"'],
  [/from ["'](\.\.\/)+hooks\/useTelemetryWebsocket["']/g, 'from "$1modules/mission-runtime"'],
  [/from ["'](\.\.\/)+hooks\/useFlightTelemetrySummary["']/g, 'from "$1modules/mission-runtime/utils/deriveTelemetry"'],
  [/from ["'](\.\.\/)+lib\/extractLatLng["']/g, 'from "$1shared/utils/extractLatLng"'],
  [/from ["'](\.\.\/)+auth["']/g, 'from "$1modules/session"'],
  [/from ["'](\.\.\/)+contexts\/AlertCenterContext["']/g, 'from "$1modules/alerts"'],
  [/from ["'](\.\.\/)+utils\/googleMaps["']/g, 'from "$1modules/maps/providers/googleMaps"'],
  [/from ["'](\.\.\/)+utils\/drawingShapes["']/g, 'from "$1modules/maps/utils/drawingShapes"'],
  [/from ["'](\.\.\/)+components\/dashboard\/Header["']/g, 'from "$1shared/layout/WorkflowHeader"'],
  [/from ["'](\.\.\/)+components\/dashboard\/InfoLabel["']/g, 'from "$1shared/ui/InfoLabel"'],
  [/from ["'](\.\.\/)+components\/dashboard\/PageLayout["']/g, 'from "$1shared/layout/PageLayout"'],
  [/from ["'](\.\.\/)+components\/shared-theme\/AppTheme["']/g, 'from "$1shared/theme/AppTheme"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/MissionCommandPanel["']/g, 'from "$1modules/mission-runtime"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/MissionPreflightPanel["']/g, 'from "$1modules/mission-runtime"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/MissionVideoPanel["']/g, 'from "$1modules/mission-runtime"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/MissionStatusChips["']/g, 'from "$1modules/mission-runtime"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/TelemetryHud["']/g, 'from "$1modules/mission-runtime"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/MissionMapViewport["']/g, 'from "$1modules/maps"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/CesiumViewControls["']/g, 'from "$1modules/maps"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/TerraDrawController["']/g, 'from "$1modules/maps"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/RouteDrawControls["']/g, 'from "$1modules/maps"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/SavedFieldsPanel["']/g, 'from "$1modules/fields"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/FieldBorderPanel["']/g, 'from "$1modules/fields"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/TaskControlFrame["']/g, 'from "$1modules/mission-workflow"'],
  [/from ["'](\.\.\/)+components\/dashboard\/tasks\/ErrorAlerts["']/g, 'from "$1shared/ui/ErrorAlerts"'],
  [/from ["'](\.\.\/)+components\/LeafletMap["']/g, 'from "$1modules/maps/adapters/LeafletMap"'],
  [/from ["'](\.\.\/)+components\/MapLibreMap["']/g, 'from "$1modules/maps/adapters/MapLibreMap"'],
  [/from ["'](\.\.\/)+components\/dashboard\/MainGrid["']/g, 'from "$1modules/dashboard/components/MainGrid"'],
  [/from ["'](\.\.\/)+components\/dashboard\/CustomizedDataGrid["']/g, 'from "$1modules/dashboard/components/CustomizedDataGrid"'],
];

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      if (entry === "node_modules") continue;
      walk(path, files);
    } else if (/\.(tsx?|jsx?)$/.test(entry)) {
      files.push(path);
    }
  }
  return files;
}

let changed = 0;
for (const file of walk(SRC)) {
  let text = readFileSync(file, "utf8");
  const before = text;
  for (const [pattern, replacement] of REPLACEMENTS) {
    text = text.replace(pattern, replacement);
  }
  if (text !== before) {
    writeFileSync(file, text);
    changed += 1;
    console.log(relative(SRC, file));
  }
}
console.log(`Updated ${changed} files`);
