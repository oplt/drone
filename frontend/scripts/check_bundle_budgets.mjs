#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const FORBIDDEN_SHELL_PRELOADS = [
  "vendor-google-maps",
  "vendor-cesium",
  "cesium",
];

export function modulePreloadHrefs(html) {
  return [...html.matchAll(/<link\b[^>]*>/gi)]
    .map(([tag]) =>
      /\brel=["']modulepreload["']/i.test(tag)
        ? tag.match(/\bhref=["']([^"']+)["']/i)?.[1]
        : undefined,
    )
    .filter(Boolean);
}

export function unexpectedMapPreloads(html) {
  return modulePreloadHrefs(html).filter((href) =>
    FORBIDDEN_SHELL_PRELOADS.some((name) => href.toLowerCase().includes(name)),
  );
}

export function assertShellHasNoMapPreloads(html) {
  const unexpected = unexpectedMapPreloads(html);
  if (unexpected.length) {
    throw new Error(
      `Application shell unexpectedly preloads map/3D chunks: ${unexpected.join(", ")}`,
    );
  }
}

function main() {
  const indexPath = resolve(process.cwd(), process.argv[2] ?? "dist/index.html");
  assertShellHasNoMapPreloads(readFileSync(indexPath, "utf8"));
  console.log("Bundle budget passed: shell has no Google Maps or Cesium preloads.");
}

if (resolve(process.argv[1] ?? "") === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}
