#!/usr/bin/env node
/**
 * Fail when frontend source files introduce or increase architecture size violations.
 * Run with --update-baseline to record current migration debt.
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

function main() {
  const updateBaseline = process.argv.includes("--update-baseline");
  const current = collectViolations();

  if (updateBaseline) {
    writeFileSync(`${BASELINE_PATH}`, `${JSON.stringify(current, null, 2)}\n`, "utf8");
    console.log(
      `Recorded ${Object.keys(current).length} existing file-size violations in baseline.`,
    );
    return 0;
  }

  const baseline = JSON.parse(readFileSync(BASELINE_PATH, "utf8"));
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

  if (regressions.length > 0) {
    console.error("File-size architecture regressions:");
    for (const regression of regressions) {
      console.error(`- ${regression}`);
    }
    return 1;
  }

  console.log(
    `File-size guard passed; ${grandfathered} baseline violations remain to extract.`,
  );
  return 0;
}

try {
  process.exitCode = main();
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
