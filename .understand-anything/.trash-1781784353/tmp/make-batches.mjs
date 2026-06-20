import { writeFileSync, readFileSync } from "node:fs";
import { dirname } from "node:path";

const scan = JSON.parse(readFileSync(".understand-anything/intermediate/scan-result.json", "utf8"));
const MAX_LINES = 1800;
const MAX_FILES = 24;

function groupKey(file) {
  const first = file.path.split("/")[0] || "";
  const second = file.path.split("/")[1] || "";
  if (first === "backend") return `backend/${second}`;
  if (first === "frontend") return `frontend/${second}`;
  if (first === "ros2_ws") return `ros2_ws/${second}`;
  return `${file.fileCategory}:${dirname(file.path)}`;
}

const grouped = new Map();
for (const file of scan.files) {
  const key = groupKey(file);
  if (!grouped.has(key)) grouped.set(key, []);
  grouped.get(key).push(file);
}

const batches = [];
for (const [, files] of [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b))) {
  let current = [];
  let lines = 0;
  for (const file of files.sort((a, b) => a.path.localeCompare(b.path))) {
    if (current.length && (current.length >= MAX_FILES || lines + file.sizeLines > MAX_LINES)) {
      batches.push(current);
      current = [];
      lines = 0;
    }
    current.push(file);
    lines += file.sizeLines;
  }
  if (current.length) batches.push(current);
}

const batchByPath = new Map();
batches.forEach((files, index) => files.forEach((file) => batchByPath.set(file.path, index + 1)));

const outputBatches = batches.map((files, index) => {
  const filePaths = new Set(files.map((file) => file.path));
  const batchImportData = {};
  const neighborMap = {};
  for (const file of files) {
    const imports = scan.importMap[file.path] || [];
    batchImportData[file.path] = imports;
    const neighbors = imports
      .filter((target) => !filePaths.has(target))
      .map((target) => ({ path: target, batchIndex: batchByPath.get(target), exports: [] }))
      .filter((entry) => entry.batchIndex);
    if (neighbors.length) neighborMap[file.path] = neighbors;
  }
  return { batchIndex: index + 1, files, batchImportData, neighborMap };
});

const result = {
  schemaVersion: 1,
  algorithm: "directory-category-fallback",
  totalFiles: scan.files.length,
  totalBatches: outputBatches.length,
  exportsByPath: Object.fromEntries(scan.files.map((file) => [file.path, []])),
  batches: outputBatches,
};

writeFileSync(".understand-anything/intermediate/batches.json", JSON.stringify(result, null, 2));
