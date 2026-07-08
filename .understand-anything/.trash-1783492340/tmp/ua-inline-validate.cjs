#!/usr/bin/env node
const fs = require('fs');
const graphPath = process.argv[2];
const outputPath = process.argv[3];
const graph = JSON.parse(fs.readFileSync(graphPath, 'utf8'));
const issues = [], warnings = [];
if (!Array.isArray(graph.nodes)) issues.push('graph.nodes is missing or not an array');
if (!Array.isArray(graph.edges)) issues.push('graph.edges is missing or not an array');
const nodeIds = new Set((graph.nodes || []).map(n => n.id));
const seen = new Set();
for (const [i, n] of (graph.nodes || []).entries()) {
  if (!n.id) issues.push(`Node[${i}] missing id`);
  if (seen.has(n.id)) issues.push(`Duplicate node ID '${n.id}'`);
  seen.add(n.id);
  if (!n.type) issues.push(`Node[${i}] '${n.id}' missing type`);
  if (!n.name) issues.push(`Node[${i}] '${n.id}' missing name`);
  if (!n.summary) issues.push(`Node[${i}] '${n.id}' missing summary`);
  if (!Array.isArray(n.tags) || !n.tags.length) issues.push(`Node[${i}] '${n.id}' missing tags`);
}
for (const [i, e] of (graph.edges || []).entries()) {
  if (!nodeIds.has(e.source)) issues.push(`Edge[${i}] source '${e.source}' not found`);
  if (!nodeIds.has(e.target)) issues.push(`Edge[${i}] target '${e.target}' not found`);
}
if (!Array.isArray(graph.layers)) issues.push('graph.layers is missing or not an array');
if (!Array.isArray(graph.tour)) issues.push('graph.tour is missing or not an array');
const fileLevel = new Set(['file', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
const assigned = new Map();
for (const layer of graph.layers || []) {
  for (const field of ['id', 'name', 'description', 'nodeIds']) {
    if (layer[field] === undefined) issues.push(`Layer missing ${field}`);
  }
  for (const id of layer.nodeIds || []) {
    if (!nodeIds.has(id)) issues.push(`Layer '${layer.id}' refs missing node '${id}'`);
    if (assigned.has(id)) warnings.push(`Node '${id}' appears in multiple layers`);
    assigned.set(id, layer.id);
  }
}
for (const n of graph.nodes || []) {
  if (fileLevel.has(n.type) && !assigned.has(n.id)) issues.push(`File node '${n.id}' not in any layer`);
}
for (const [i, step] of (graph.tour || []).entries()) {
  for (const field of ['order', 'title', 'description', 'nodeIds']) {
    if (step[field] === undefined) issues.push(`Tour step[${i}] missing ${field}`);
  }
  for (const id of step.nodeIds || []) {
    if (!nodeIds.has(id)) issues.push(`Tour step[${i}] refs missing node '${id}'`);
  }
}
const stats = {
  totalNodes: graph.nodes.length,
  totalEdges: graph.edges.length,
  totalLayers: graph.layers.length,
  tourSteps: graph.tour.length,
  nodeTypes: graph.nodes.reduce((a, n) => (a[n.type] = (a[n.type] || 0) + 1, a), {}),
  edgeTypes: graph.edges.reduce((a, e) => (a[e.type] = (a[e.type] || 0) + 1, a), {}),
};
fs.writeFileSync(outputPath, JSON.stringify({ issues, warnings, stats }, null, 2));
