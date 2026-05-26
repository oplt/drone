#!/usr/bin/env node
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";

const SRC = join(import.meta.dirname, "../src");

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      if (entry === "node_modules") continue;
      walk(path, files);
    } else if (/\.(tsx?)$/.test(entry)) {
      files.push(path);
    }
  }
  return files;
}

function relImport(fromFile, targetUnderSrc) {
  const fromDir = dirname(fromFile);
  const target = join(SRC, targetUnderSrc);
  let rel = relative(fromDir, target).replaceAll("\\", "/");
  if (!rel.startsWith(".")) rel = `./${rel}`;
  return rel;
}

const TARGETS = [
  { pattern: /from ["']\.\.\/shared\//g, target: "shared" },
  { pattern: /from ["']\.\.\/modules\//g, target: "modules" },
];

let changed = 0;
for (const file of walk(SRC)) {
  let text = readFileSync(file, "utf8");
  const before = text;
  for (const { pattern, target } of TARGETS) {
    text = text.replace(pattern, (match) => {
      const prefix = match.match(/from ["']([^"']*)/)[1];
      const subpath = text.slice(text.indexOf(match) + match.length); // unreliable
      return match;
    });
  }
}

// Simpler: fix known wrong prefix in modules/** and pages/** 
for (const file of walk(SRC)) {
  let text = readFileSync(file, "utf8");
  const before = text;
  const fileRel = relative(SRC, file);
  const depth = fileRel.split("/").length - 1;
  const correctPrefix = "../".repeat(depth);

  text = text.replace(/from ["']\.\.\/shared\//g, `from "${correctPrefix}shared/`);
  text = text.replace(/from ["']\.\.\/modules\//g, `from "${correctPrefix}modules/`);

  if (text !== before) {
    writeFileSync(file, text);
    changed += 1;
  }
}
console.log(`Fixed depth in ${changed} files`);
