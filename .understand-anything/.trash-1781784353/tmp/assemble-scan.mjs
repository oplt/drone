import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, extname, join } from "node:path";

const root = process.cwd();
const scan = JSON.parse(readFileSync(".understand-anything/tmp/ua-scan-files.json", "utf8"));
const fileSet = new Set(scan.files.map((file) => file.path));

function read(path) {
  return existsSync(path) ? readFileSync(path, "utf8") : "";
}

function packageJson(path) {
  if (!existsSync(path)) return {};
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return {};
  }
}

function hasDependency(pkg, name) {
  return Boolean(pkg.dependencies?.[name] || pkg.devDependencies?.[name]);
}

function resolveImport(fromFile, specifier) {
  if (!specifier || !specifier.startsWith(".")) return null;
  const base = join(dirname(fromFile), specifier).replace(/\\/g, "/");
  const candidates = [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    `${base}.js`,
    `${base}.jsx`,
    `${base}.py`,
    `${base}/index.ts`,
    `${base}/index.tsx`,
    `${base}/index.js`,
    `${base}/__init__.py`,
  ].map((candidate) => candidate.replace(/^\.\//, ""));
  return candidates.find((candidate) => fileSet.has(candidate)) || null;
}

function importsFor(file) {
  if (!["typescript", "javascript", "python"].includes(file.language)) return [];
  const raw = read(join(root, file.path));
  const out = new Set();
  if (file.language === "python") {
    for (const match of raw.matchAll(/^\s*from\s+(\.+[\w.]*)\s+import\s+/gm)) {
      const rel = match[1].replaceAll(".", "/");
      const resolved = resolveImport(file.path, rel);
      if (resolved) out.add(resolved);
    }
  } else {
    const patterns = [
      /(?:import|export)\s+(?:[^'"]+\s+from\s+)?["']([^"']+)["']/g,
      /import\(["']([^"']+)["']\)/g,
      /require\(["']([^"']+)["']\)/g,
    ];
    for (const pattern of patterns) {
      for (const match of raw.matchAll(pattern)) {
        const resolved = resolveImport(file.path, match[1]);
        if (resolved) out.add(resolved);
      }
    }
  }
  return [...out].sort();
}

const frontendPkg = packageJson("frontend/package.json");
const frameworks = new Set();
if (hasDependency(frontendPkg, "react")) frameworks.add("React");
if (hasDependency(frontendPkg, "vite")) frameworks.add("Vite");
if (hasDependency(frontendPkg, "vitest")) frameworks.add("Vitest");
if (hasDependency(frontendPkg, "@react-three/fiber") || hasDependency(frontendPkg, "three")) {
  frameworks.add("Three.js");
}
const requirements = read("backend/requirements.txt");
if (/^fastapi==/m.test(requirements)) frameworks.add("FastAPI");
if (/^celery==/m.test(requirements)) frameworks.add("Celery");
if (/^SQLAlchemy==/m.test(requirements)) frameworks.add("SQLAlchemy");
if (/^alembic==/m.test(requirements)) frameworks.add("Alembic");
if (existsSync("docker-compose.yml")) frameworks.add("Docker Compose");
if (existsSync("backend/Dockerfile") || existsSync("frontend/Dockerfile")) frameworks.add("Docker");

const importMap = {};
for (const file of scan.files) importMap[file.path] = importsFor(file);

const languages = Object.keys(scan.stats.byLanguage).sort();
const result = {
  name: "Drone Operations Platform",
  description:
    "A full-stack drone mission control application with a FastAPI backend, React operator dashboard, and optional ROS 2 / Gazebo simulation integration.",
  languages,
  frameworks: [...frameworks].sort(),
  files: scan.files,
  totalFiles: scan.totalFiles,
  filteredByIgnore: scan.filteredByIgnore,
  estimatedComplexity: scan.estimatedComplexity,
  importMap,
};

writeFileSync(".understand-anything/intermediate/scan-result.json", JSON.stringify(result, null, 2));
