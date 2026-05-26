#!/usr/bin/env node
/**
 * Fail when ESLint introduces new findings beyond the recorded baseline.
 * Run with --update-baseline to record current migration debt.
 */

import { execSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = resolve(__dirname, "..");
const BASELINE_PATH = join(__dirname, "eslint_baseline.json");

export function collectFindings() {
  const output = execSync("npx eslint . -f json", {
    cwd: FRONTEND_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  const start = output.indexOf("[");
  if (start < 0) {
    return {};
  }
  const files = JSON.parse(output.slice(start));
  const counts = {};
  for (const file of files) {
    const relativePath = file.filePath.replace(`${FRONTEND_ROOT}/`, "frontend/");
    for (const message of file.messages) {
      const key = `${relativePath}|${message.ruleId ?? "unknown"}`;
      counts[key] = (counts[key] ?? 0) + 1;
    }
  }
  return counts;
}

function summarizeByModule(counts) {
  const modules = {};
  for (const [key, count] of Object.entries(counts)) {
    const path = key.split("|")[0].replace("frontend/src/", "");
    let moduleName = "root";
    if (path.startsWith("pages/")) moduleName = "pages";
    else if (path.startsWith("components/dashboard/tasks/"))
      moduleName = "mission-runtime (tasks)";
    else if (path.startsWith("components/dashboard/")) moduleName = "components/dashboard";
    else if (path.startsWith("components/")) moduleName = "components";
    else if (path.startsWith("hooks/")) moduleName = "hooks";
    else if (path.startsWith("utils/")) moduleName = "utils";
    else if (path.startsWith("contexts/")) moduleName = "contexts";
    else if (path.startsWith("lib/")) moduleName = "lib";
    else if (path.includes("/")) moduleName = path.split("/")[0];
    modules[moduleName] = (modules[moduleName] ?? 0) + count;
  }
  return modules;
}

function main() {
  const updateBaseline = process.argv.includes("--update-baseline");
  let current;
  try {
    current = collectFindings();
  } catch (error) {
    const stderr = error?.stderr?.toString?.() ?? "";
    const stdout = error?.stdout?.toString?.() ?? "";
    const combined = `${stdout}${stderr}`;
    const start = combined.indexOf("[");
    if (start < 0) {
      console.error(combined || error);
      return 1;
    }
    current = {};
    const files = JSON.parse(combined.slice(start));
    for (const file of files) {
      const relativePath = file.filePath.replace(`${FRONTEND_ROOT}/`, "frontend/");
      for (const message of file.messages) {
        const key = `${relativePath}|${message.ruleId ?? "unknown"}`;
        current[key] = (current[key] ?? 0) + 1;
      }
    }
  }

  if (updateBaseline) {
    const sorted = Object.fromEntries(
      Object.entries(current).sort(([a], [b]) => a.localeCompare(b)),
    );
    writeFileSync(BASELINE_PATH, `${JSON.stringify(sorted, null, 2)}\n`, "utf8");
    const total = Object.values(current).reduce((sum, value) => sum + value, 0);
    console.log(`Recorded ${total} existing ESLint findings in baseline.`);
    const byModule = summarizeByModule(current);
    for (const [moduleName, count] of Object.entries(byModule).sort(
      (a, b) => b[1] - a[1],
    )) {
      console.log(`  ${moduleName}: ${count}`);
    }
    return 0;
  }

  const baseline = JSON.parse(readFileSync(BASELINE_PATH, "utf8"));
  const regressions = Object.entries(current)
    .filter(([key, count]) => count > (baseline[key] ?? 0))
    .map(
      ([key, count]) => `${key}: ${count} findings (baseline ${baseline[key] ?? 0})`,
    );

  if (regressions.length > 0) {
    console.error("ESLint regressions:");
    for (const regression of regressions) {
      console.error(`- ${regression}`);
    }
    return 1;
  }

  const total = Object.values(baseline).reduce((sum, value) => sum + value, 0);
  console.log(`ESLint guard passed; ${total} baseline findings remain to fix.`);
  return 0;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  process.exitCode = main();
}
