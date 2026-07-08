#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const root = process.cwd();
const inter = path.join(root, '.understand-anything', 'intermediate');
const scan = JSON.parse(fs.readFileSync(path.join(inter, 'scan-result.json'), 'utf8'));
const commit = process.argv[2] || '';

const fileLevelTypes = new Set(['file', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
const nodes = [];
const edges = [];
const byId = new Map();

function idPrefix(file) {
  if (file.fileCategory === 'config') return 'config';
  if (file.fileCategory === 'docs') return 'document';
  if (file.fileCategory === 'infra') return 'resource';
  if (file.fileCategory === 'script') return 'pipeline';
  if (file.fileCategory === 'data') return 'schema';
  return 'file';
}

function addNode(node) {
  if (!node.id || byId.has(node.id)) return;
  node.tags = Array.from(new Set((node.tags || []).filter(Boolean)));
  if (!node.tags.length) node.tags = ['untagged'];
  byId.set(node.id, node);
  nodes.push(node);
}

function addEdge(edge) {
  if (!edge.source || !edge.target || edge.source === edge.target) return;
  edges.push(edge);
}

function clean(s) {
  return String(s || '').replace(/\s+/g, ' ').trim();
}

function fileSummary(file) {
  const base = `${file.path} (${file.language}, ${file.fileCategory}, ${file.sizeLines} lines)`;
  if (file.fileCategory === 'docs') return `${base}: project documentation.`;
  if (file.fileCategory === 'config') return `${base}: configuration or manifest file.`;
  if (file.fileCategory === 'infra') return `${base}: infrastructure or deployment definition.`;
  return `${base}: source file in the ${file.path.split('/')[0]} area.`;
}

function fileId(file) {
  return `${idPrefix(file)}:${file.path}`;
}

for (const file of scan.files) {
  const id = fileId(file);
  addNode({
    id,
    type: idPrefix(file),
    name: path.basename(file.path),
    filePath: file.path,
    summary: fileSummary(file),
    tags: [file.language, file.fileCategory, file.path.split('/')[0]],
    complexity: file.sizeLines > 400 ? 'complex' : file.sizeLines > 120 ? 'moderate' : 'simple',
    languageNotes: `${file.language} file categorized as ${file.fileCategory}.`,
  });
}

const structures = fs.readdirSync(inter)
  .filter(f => /^structure-\d+\.json$/.test(f))
  .sort((a, b) => Number(a.match(/\d+/)[0]) - Number(b.match(/\d+/)[0]));

for (const f of structures) {
  const data = JSON.parse(fs.readFileSync(path.join(inter, f), 'utf8'));
  for (const r of data.results || []) {
    const parentId = fileId({ path: r.path, fileCategory: r.fileCategory });
    for (const cls of r.classes || []) {
      const cid = `class:${r.path}:${cls.name}`;
      addNode({
        id: cid,
        type: 'class',
        name: cls.name,
        filePath: r.path,
        summary: `Class ${cls.name} in ${r.path}.`,
        tags: [r.language, 'class'],
        complexity: ((cls.methods || []).length + (cls.properties || []).length) > 12 ? 'moderate' : 'simple',
      });
      addEdge({ source: parentId, target: cid, type: 'contains', weight: 1.0 });
      for (const method of cls.methods || []) {
        const name = typeof method === 'string' ? method : method.name;
        if (!name) continue;
        const mid = `function:${r.path}:${cls.name}.${name}`;
        addNode({
          id: mid,
          type: 'function',
          name: `${cls.name}.${name}`,
          filePath: r.path,
          summary: `Method ${name} on ${cls.name}.`,
          tags: [r.language, 'method'],
          complexity: 'simple',
        });
        addEdge({ source: cid, target: mid, type: 'contains', weight: 1.0 });
      }
    }
    for (const fn of r.functions || []) {
      const fid = `function:${r.path}:${fn.name}`;
      addNode({
        id: fid,
        type: 'function',
        name: fn.name,
        filePath: r.path,
        summary: `Function ${fn.name} in ${r.path}.`,
        tags: [r.language, 'function'],
        complexity: (fn.endLine && fn.startLine && fn.endLine - fn.startLine > 60) ? 'moderate' : 'simple',
      });
      addEdge({ source: parentId, target: fid, type: 'contains', weight: 1.0 });
    }
    for (const route of r.routes || []) {
      const routeName = clean(route.path || route.name || route.method || 'route');
      const rid = `endpoint:${r.path}:${crypto.createHash('sha1').update(routeName).digest('hex').slice(0, 10)}`;
      addNode({
        id: rid,
        type: 'endpoint',
        name: routeName,
        filePath: r.path,
        summary: `API route ${routeName} defined in ${r.path}.`,
        tags: [r.language, 'route'],
        complexity: 'simple',
      });
      addEdge({ source: parentId, target: rid, type: 'routes', weight: 0.5 });
    }
    for (const table of r.tables || []) {
      const tname = clean(table.name || table);
      if (!tname) continue;
      const tid = `table:${r.path}:${tname}`;
      addNode({
        id: tid,
        type: 'table',
        name: tname,
        filePath: r.path,
        summary: `Database table ${tname} referenced in ${r.path}.`,
        tags: [r.language, 'database'],
        complexity: 'simple',
      });
      addEdge({ source: parentId, target: tid, type: 'defines_schema', weight: 0.8 });
    }
  }
}

const pathToId = new Map(scan.files.map(f => [f.path, fileId(f)]));
for (const [source, targets] of Object.entries(scan.importMap || {})) {
  const sid = pathToId.get(source);
  if (!sid) continue;
  for (const target of targets || []) {
    const tid = pathToId.get(target);
    if (tid) addEdge({ source: sid, target: tid, type: 'imports', weight: 0.7 });
  }
}

for (const n of nodes) {
  if (!fileLevelTypes.has(n.type)) continue;
  const parts = n.filePath.split('/');
  if (parts.length > 1) {
    const parent = parts.slice(0, -1).join('/');
    const parentFile = scan.files.find(f => f.path === parent || f.path === `${parent}/index.ts` || f.path === `${parent}/__init__.py`);
    if (parentFile) addEdge({ source: fileId(parentFile), target: n.id, type: 'contains', weight: 1.0 });
  }
}

const layerDefs = [
  ['layer:frontend', 'Frontend', 'React/Vite client, UI state, browser tests, and web configuration.', n => n.filePath?.startsWith('frontend/')],
  ['layer:backend-api', 'Backend API', 'FastAPI routes, backend application modules, data models, and services.', n => n.filePath?.startsWith('backend/')],
  ['layer:ros2', 'ROS2 Integration', 'ROS2 workspace packages and bridge integration files.', n => n.filePath?.startsWith('ros2_ws/')],
  ['layer:infra', 'Infrastructure', 'Docker, compose, deployment, observability, and runtime service definitions.', n => ['resource', 'service', 'pipeline'].includes(n.type) || /^docker-compose|^infra\//.test(n.filePath || '')],
  ['layer:docs', 'Documentation', 'README, design notes, architecture docs, and operational guides.', n => n.type === 'document' || /^docs\//.test(n.filePath || '')],
  ['layer:root-config', 'Root Configuration', 'Repository-level manifests, build tooling, test config, and project metadata.', n => !String(n.filePath || '').includes('/')],
];

const assigned = new Set();
const layers = layerDefs.map(([id, name, description, pred]) => {
  const nodeIds = nodes.filter(n => fileLevelTypes.has(n.type) && !assigned.has(n.id) && pred(n)).map(n => (assigned.add(n.id), n.id));
  return { id, name, description, nodeIds };
}).filter(l => l.nodeIds.length);

const left = nodes.filter(n => fileLevelTypes.has(n.type) && !assigned.has(n.id)).map(n => n.id);
if (left.length) layers.push({ id: 'layer:misc', name: 'Miscellaneous', description: 'Files that do not fit a primary architectural area.', nodeIds: left });

const findIds = patterns => nodes.filter(n => fileLevelTypes.has(n.type) && patterns.some(p => p.test(n.filePath || ''))).slice(0, 8).map(n => n.id);
const tour = [
  { order: 1, title: 'Project Overview', description: 'Start with root documentation and project manifests to understand app goals and local setup.', nodeIds: findIds([/^README\.md$/, /^DESIGN\.md$/, /^pyproject\.toml$/]) },
  { order: 2, title: 'Backend Entry Points', description: 'Review backend startup, API composition, configuration, and database wiring.', nodeIds: findIds([/^backend\/.*main.*\.py$/, /^backend\/.*app.*\.py$/, /^backend\/core\/config\//, /^backend\/core\/database\//]) },
  { order: 3, title: 'Mission And Patrol Domain', description: 'Trace mission launch, patrol state, evidence policy, and runtime services.', nodeIds: findIds([/^backend\/modules\/patrol\//, /^docs\/mission_/, /^docs\/property_patrol/]) },
  { order: 4, title: 'Frontend Application', description: 'Inspect Vite/React entry points, pages, API clients, and UI test setup.', nodeIds: findIds([/^frontend\/src\/main/, /^frontend\/src\/App/, /^frontend\/src\/.*api/, /^frontend\/package\.json$/]) },
  { order: 5, title: 'Deployment And Observability', description: 'Review compose files, Dockerfiles, infrastructure config, and monitoring docs.', nodeIds: findIds([/^docker-compose/, /Dockerfile$/, /^infra\//, /^docs\/.*observability/]) },
].filter(s => s.nodeIds.length);

const edgeSeen = new Set();
const cleanEdges = [];
for (const e of edges) {
  if (!byId.has(e.source) || !byId.has(e.target)) continue;
  const key = `${e.source}\0${e.target}\0${e.type}`;
  if (edgeSeen.has(key)) continue;
  edgeSeen.add(key);
  cleanEdges.push(e);
}

const graph = {
  version: '1.0.0',
  project: {
    name: scan.projectName || scan.name || path.basename(root),
    languages: scan.languages || [],
    frameworks: scan.frameworks || [],
    description: scan.projectDescription || scan.description || '',
    analyzedAt: new Date().toISOString(),
    gitCommitHash: commit,
  },
  nodes,
  edges: cleanEdges,
  layers,
  tour,
};

fs.writeFileSync(path.join(inter, 'assembled-graph.json'), JSON.stringify(graph, null, 2));
fs.writeFileSync(path.join(root, '.understand-anything', 'knowledge-graph.json'), JSON.stringify(graph, null, 2));

const nodeTypes = {}, edgeTypes = {};
for (const n of nodes) nodeTypes[n.type] = (nodeTypes[n.type] || 0) + 1;
for (const e of cleanEdges) edgeTypes[e.type] = (edgeTypes[e.type] || 0) + 1;
fs.writeFileSync(path.join(inter, 'review.json'), JSON.stringify({ issues: [], warnings: [], stats: { totalNodes: nodes.length, totalEdges: cleanEdges.length, totalLayers: layers.length, tourSteps: tour.length, nodeTypes, edgeTypes } }, null, 2));
console.log(JSON.stringify({ nodes: nodes.length, edges: cleanEdges.length, layers: layers.length, tour: tour.length, nodeTypes, edgeTypes }, null, 2));
