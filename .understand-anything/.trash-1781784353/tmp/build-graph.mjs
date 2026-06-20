import { readFileSync, writeFileSync } from "node:fs";

const scan = JSON.parse(readFileSync(".understand-anything/intermediate/scan-result.json", "utf8"));
const commit = readFileSync(".understand-anything/tmp/git-commit.txt", "utf8").trim();
const analyzedAt = new Date().toISOString();

const nodeTypeByCategory = {
  code: "file",
  config: "config",
  docs: "document",
  infra: "service",
  data: "schema",
  script: "pipeline",
  markup: "file",
};

function nodeId(file) {
  return `${nodeTypeByCategory[file.fileCategory] || "file"}:${file.path}`;
}

function layerFor(path) {
  if (path.startsWith("backend/entrypoints/")) return "layer:backend-entrypoints";
  if (path.startsWith("backend/modules/")) return "layer:backend-domain-modules";
  if (path.startsWith("backend/infrastructure/")) return "layer:backend-infrastructure";
  if (path.startsWith("backend/core/")) return "layer:backend-core";
  if (path.startsWith("backend/tests/")) return "layer:backend-tests";
  if (path.startsWith("backend/")) return "layer:backend-support";
  if (path.startsWith("frontend/src/modules/")) return "layer:frontend-feature-modules";
  if (path.startsWith("frontend/src/shared/")) return "layer:frontend-shared";
  if (path.startsWith("frontend/src/app/")) return "layer:frontend-app-shell";
  if (path.startsWith("frontend/src/")) return "layer:frontend-source";
  if (path.startsWith("frontend/")) return "layer:frontend-tooling";
  if (path.startsWith("ros2_ws/")) return "layer:ros2-simulation";
  if (path.startsWith("docs/") || path.endsWith(".md") || path.endsWith(".txt")) return "layer:documentation";
  return "layer:project-operations";
}

const layerDefinitions = {
  "layer:backend-entrypoints": ["Backend Entrypoints", "FastAPI application startup, worker entrypoints, and CLI adapters."],
  "layer:backend-domain-modules": ["Backend Domain Modules", "Mission, telemetry, mapping, warehouse, and operational backend APIs and domain services."],
  "layer:backend-infrastructure": ["Backend Infrastructure", "Persistence, messaging, vehicle, camera, photogrammetry, and external integration adapters."],
  "layer:backend-core": ["Backend Core", "Shared backend settings, database, security, logging, and cross-cutting runtime utilities."],
  "layer:backend-tests": ["Backend Tests", "Pytest coverage for backend modules and integration boundaries."],
  "layer:backend-support": ["Backend Support", "Backend configuration, migrations, scripts, and package metadata."],
  "layer:frontend-app-shell": ["Frontend App Shell", "React routing, application shell, and top-level browser entry points."],
  "layer:frontend-feature-modules": ["Frontend Feature Modules", "Operator-facing mission, warehouse, maps, telemetry, dashboard, and workflow UI modules."],
  "layer:frontend-shared": ["Frontend Shared", "Reusable frontend UI, API clients, hooks, styles, and utilities."],
  "layer:frontend-source": ["Frontend Source", "Frontend source files outside the main app/module/shared boundaries."],
  "layer:frontend-tooling": ["Frontend Tooling", "Vite, TypeScript, linting, tests, Docker, and frontend operational configuration."],
  "layer:ros2-simulation": ["ROS 2 Simulation", "Gazebo and ROS 2 bridge packages, launch files, and simulation configuration."],
  "layer:documentation": ["Documentation", "Repository guides, architecture notes, setup documentation, and operational plans."],
  "layer:project-operations": ["Project Operations", "Repository-level Makefiles, Docker Compose, process files, and project configuration."],
};

function summaryFor(file) {
  const name = file.path.split("/").pop();
  if (file.fileCategory === "docs") return `${name} documents part of the Drone Operations Platform.`;
  if (file.fileCategory === "infra") return `${name} defines infrastructure, process, container, or deployment behavior.`;
  if (file.fileCategory === "config") return `${name} configures tooling or runtime behavior.`;
  if (file.fileCategory === "script") return `${name} provides automation or operational scripting.`;
  if (file.fileCategory === "data") return `${name} defines data, schema, or migration artifacts.`;
  return `${name} is a ${file.language} source file in the Drone Operations Platform.`;
}

const nodes = scan.files.map((file) => ({
  id: nodeId(file),
  type: nodeTypeByCategory[file.fileCategory] || "file",
  name: file.path.split("/").pop(),
  filePath: file.path,
  summary: summaryFor(file),
  tags: [file.language, file.fileCategory, layerFor(file.path).replace("layer:", "")],
  complexity:
    file.sizeLines > 600 ? "complex" : file.sizeLines > 180 ? "moderate" : "simple",
}));

const idByPath = new Map(scan.files.map((file) => [file.path, nodeId(file)]));
const edges = [];
const edgeKeys = new Set();

function addEdge(source, target, type, weight = 0.5, label = "") {
  if (!source || !target || source === target) return;
  const key = `${source}|${target}|${type}`;
  if (edgeKeys.has(key)) return;
  edgeKeys.add(key);
  edges.push({ source, target, type, weight, ...(label ? { label } : {}) });
}

for (const [sourcePath, targets] of Object.entries(scan.importMap)) {
  for (const targetPath of targets) addEdge(idByPath.get(sourcePath), idByPath.get(targetPath), "imports", 0.7);
}

const readme = idByPath.get("README.md");
for (const file of scan.files) {
  const id = nodeId(file);
  if (readme && id !== readme && (file.path.startsWith("backend/") || file.path.startsWith("frontend/") || file.path.startsWith("ros2_ws/"))) {
    addEdge(readme, id, "documents", 0.5);
  }
  if (file.fileCategory === "config") {
    const prefix = file.path.split("/").slice(0, -1).join("/");
    for (const target of scan.files) {
      if (target.fileCategory === "code" && target.path.startsWith(prefix ? `${prefix}/` : "")) {
        addEdge(id, nodeId(target), "configures", 0.6);
      }
    }
  }
  if (file.fileCategory === "infra") {
    const prefix = file.path.startsWith("backend/") ? "backend/" : file.path.startsWith("frontend/") ? "frontend/" : "";
    for (const target of scan.files) {
      if (prefix && target.fileCategory === "code" && target.path.startsWith(prefix)) {
        addEdge(id, nodeId(target), "deploys", 0.7);
      }
    }
  }
}

for (const test of scan.files.filter((file) => /(^|\/)(tests?|__tests__|e2e)\//.test(file.path) || /\.(test|spec)\./.test(file.path))) {
  const stem = test.path
    .replace(/^backend\/tests\//, "backend/")
    .replace(/^frontend\/src\/.*?__tests__\//, "frontend/src/")
    .replace(/\.(test|spec)\.[^.]+$/, "")
    .replace(/_test\.py$/, ".py");
  const candidate = scan.files.find((file) => file.path !== test.path && file.path.includes(stem.split("/").pop().replace(/\.[^.]+$/, "")));
  if (candidate) addEdge(nodeId(candidate), nodeId(test), "tested_by", 0.5);
}

const layerNodes = new Map();
for (const file of scan.files) {
  const layerId = layerFor(file.path);
  if (!layerNodes.has(layerId)) layerNodes.set(layerId, []);
  layerNodes.get(layerId).push(nodeId(file));
}
const layers = [...layerNodes.entries()].map(([id, nodeIds]) => {
  const [name, description] = layerDefinitions[id];
  return { id, name, description, nodeIds };
});

const tour = [
  {
    order: 1,
    title: "Project Overview",
    description: "Start with the repository README and top-level process files to understand the platform purpose and local development workflow.",
    nodeIds: ["README.md", "docker-compose.yml", "Makefile"].map((path) => idByPath.get(path)).filter(Boolean),
  },
  {
    order: 2,
    title: "Backend API Runtime",
    description: "Follow the FastAPI entrypoints into backend core services, domain modules, persistence, telemetry, and vehicle integrations.",
    nodeIds: scan.files.filter((file) => file.path.startsWith("backend/entrypoints/") || file.path.startsWith("backend/core/")).slice(0, 20).map(nodeId),
  },
  {
    order: 3,
    title: "Frontend Operator Console",
    description: "Inspect the React app shell, feature modules, shared UI, and Vite configuration that power the operator dashboard.",
    nodeIds: scan.files.filter((file) => file.path.startsWith("frontend/src/app/") || file.path.startsWith("frontend/src/modules/") || file.path === "frontend/vite.config.ts").slice(0, 20).map(nodeId),
  },
  {
    order: 4,
    title: "Simulation And Mapping",
    description: "Review ROS 2 bridge files, warehouse scanning code, live-map streaming, and photogrammetry orchestration paths.",
    nodeIds: scan.files.filter((file) => /ros2_ws|warehouse|map|photogrammetry/i.test(file.path)).slice(0, 24).map(nodeId),
  },
  {
    order: 5,
    title: "Quality And Operations",
    description: "Close with tests, linting, observability, Docker, and deployment configuration that support running the platform.",
    nodeIds: scan.files.filter((file) => /tests?|pytest|eslint|docker|observability|grafana|Makefile|Procfile/i.test(file.path)).slice(0, 24).map(nodeId),
  },
];

const graph = {
  version: "1.0.0",
  project: {
    name: scan.name,
    languages: scan.languages,
    frameworks: scan.frameworks,
    description: scan.description,
    analyzedAt,
    gitCommitHash: commit,
  },
  nodes,
  edges,
  layers,
  tour,
};

writeFileSync(".understand-anything/intermediate/assembled-graph.json", JSON.stringify(graph, null, 2));
writeFileSync(".understand-anything/knowledge-graph.json", JSON.stringify(graph, null, 2));
writeFileSync(
  ".understand-anything/meta.json",
  JSON.stringify(
    {
      lastAnalyzedAt: analyzedAt,
      gitCommitHash: commit,
      version: "1.0.0",
      analyzedFiles: scan.files.length,
    },
    null,
    2,
  ),
);
