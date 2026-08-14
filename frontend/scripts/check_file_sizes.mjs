#!/usr/bin/env node
/**
 * Fail when frontend source files introduce or increase architecture size violations.
 * Run with --update-baseline to record current migration debt.
 * Run with --prune-baseline to drop entries for files now at or below their limit.
 */

import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = resolve(__dirname, "..");
const REPO_ROOT = resolve(FRONTEND_ROOT, "..");
const SRC_ROOT = join(FRONTEND_ROOT, "src");
const BASELINE_PATH = join(__dirname, "file_size_baseline.json");

const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"]);

export function effectiveLines(text) {
  return text
    .split("\n")
    .filter((line) => line.trim() && !line.trim().startsWith("//")).length;
}

export function limitFor(relativePath) {
  if (
    relativePath.includes(
      "/modules/agriculture/workflows/",
    )
  ) {
    return 400;
  }
  if (relativePath.includes("/pages/") || relativePath.includes("/views/")) {
    return 180;
  }
  if (relativePath.includes("/hooks/")) {
    return 160;
  }
  if (relativePath.includes("/api/")) {
    return 220;
  }
  if (
    relativePath.includes("/types.") ||
    relativePath.endsWith("/types.ts") ||
    relativePath.endsWith("/types.tsx")
  ) {
    return 180;
  }
  if (relativePath.includes("/components/")) {
    return 220;
  }
  if (relativePath.includes("/utils/")) {
    return 180;
  }
  return 400;
}

function walkSourceFiles(directory, files = []) {
  for (const entry of readdirSync(directory)) {
    const absolutePath = join(directory, entry);
    if (statSync(absolutePath).isDirectory()) {
      walkSourceFiles(absolutePath, files);
      continue;
    }
    if (SOURCE_EXTENSIONS.has(entry.slice(entry.lastIndexOf(".")))) {
      files.push(absolutePath);
    }
  }
  return files;
}

export function collectViolations() {
  const violations = {};
  for (const absolutePath of walkSourceFiles(SRC_ROOT)) {
    const relativePath = relative(REPO_ROOT, absolutePath).replaceAll("\\", "/");
    const count = effectiveLines(readFileSync(absolutePath, "utf8"));
    const limit = limitFor(relativePath);
    if (count > limit) {
      violations[relativePath] = { effective_lines: count, limit };
    }
  }
  return violations;
}

export function evaluateAgainstBaseline(current, baseline) {
  const regressions = [];
  let grandfathered = 0;

  for (const [path, violation] of Object.entries(current)) {
    const permitted = baseline[path];
    if (
      permitted !== undefined &&
      violation.effective_lines <= permitted.effective_lines
    ) {
      grandfathered += 1;
      continue;
    }
    const prior = permitted?.effective_lines ?? 0;
    regressions.push(
      `${path}: ${violation.effective_lines} effective lines (limit ${violation.limit}, baseline ${prior})`,
    );
  }

  const stale = Object.keys(baseline)
    .filter((path) => !(path in current))
    .sort();

  return { regressions, stale, grandfathered };
}

export function pruneBaseline(baseline, current) {
  const pruned = {};
  for (const path of Object.keys(baseline).sort()) {
    if (path in current) {
      pruned[path] = baseline[path];
    }
  }
  return pruned;
}

function main() {
  const updateBaseline = process.argv.includes("--update-baseline");
  const pruneBaselineFlag = process.argv.includes("--prune-baseline");
  const current = collectViolations();

  if (updateBaseline) {
    writeFileSync(`${BASELINE_PATH}`, `${JSON.stringify(current, null, 2)}\n`, "utf8");
    console.log(
      `Recorded ${Object.keys(current).length} existing file-size violations in baseline.`,
    );
    return 0;
  }

  if (pruneBaselineFlag) {
    const baseline = JSON.parse(readFileSync(BASELINE_PATH, "utf8"));
    const pruned = pruneBaseline(baseline, current);
    const removed = Object.keys(baseline).filter((path) => !(path in pruned));
    writeFileSync(`${BASELINE_PATH}`, `${JSON.stringify(pruned, null, 2)}\n`, "utf8");
    console.log(`Pruned ${removed.length} resolved baseline entries.`);
    for (const path of removed) {
      console.log(`- ${path}`);
    }
    return 0;
  }

  const baseline = JSON.parse(readFileSync(BASELINE_PATH, "utf8"));
  const { regressions, stale, grandfathered } = evaluateAgainstBaseline(current, baseline);

  let failed = false;
  if (stale.length > 0) {
    failed = true;
    console.error(
      "Stale file-size baseline entries (file is now at or below limit — remove them):",
    );
    for (const path of stale) {
      console.error(`- ${path}`);
    }
    console.error("Run: node scripts/check_file_sizes.mjs --prune-baseline");
  }

  if (regressions.length > 0) {
    failed = true;
    console.error("File-size architecture regressions:");
    for (const regression of regressions) {
      console.error(`- ${regression}`);
    }
  }

  if (failed) {
    return 1;
  }

  console.log(
    `File-size guard passed; ${grandfathered} baseline violations remain to extract.`,
  );
  return 0;
}

if (resolve(process.argv[1] ?? "") === fileURLToPath(import.meta.url)) {
  try {
    process.exitCode = main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}
