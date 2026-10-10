const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const shell = fs.readFileSync(path.join(__dirname, '..', 'web', 'shell.js'), 'utf8');
const app = fs.readFileSync(path.join(__dirname, '..', 'web', 'app.js'), 'utf8');
const tritonView = fs.readFileSync(path.join(__dirname, '..', 'web', 'triton-view.js'), 'utf8');

test('P-002: shell modules load in dependency order before app.js', () => {
  const scripts = [...html.matchAll(/<script src="([^"]+)" defer>/g)].map(m => m[1]);
  const idx = name => scripts.indexOf(name);
  assert.ok(idx('catalog.js') > -1, 'catalog.js loaded');
  assert.ok(idx('query-state.js') > idx('catalog.js'), 'query-state after catalog');
  assert.ok(idx('workbench.js') > idx('query-state.js'), 'workbench after query-state');
  assert.ok(idx('status-view.js') > idx('workbench.js'), 'status-view after workbench');
  assert.ok(idx('shell.js') > idx('status-view.js'), 'shell after status-view');
  assert.ok(idx('workbench-view.js') > idx('shell.js'), 'workbench-view after shell');
  assert.ok(idx('shell-init.js') > idx('workbench-view.js'), 'shell-init after workbench-view');
  assert.ok(idx('app.js') > idx('shell-init.js'), 'app.js loads last');
});

test('P-001: index.html carries a workbench view container and nav entry', () => {
  assert.match(html, /<section id="workbench-view"/);
  assert.match(html, /<a href="#workbench"[^>]*data-nav="workbench"/);
});

test('P-011: app.js routes the new workbench/projects scheme into the workbench view', () => {
  assert.match(app, /function navigate\(hash\)\{const newRoute=Router\.parseRoute\(hash\)/);
  assert.match(app, /function applyWorkbenchRoute\(route\)/);
  assert.match(app, /\$\('workbench-view'\)\.hidden=false/);
  assert.match(app, /for\(const id of \['ubs-view','ubs-repo-view','triton-view','method-view'\]\)\$\(id\)\.hidden=true/);
  assert.match(app, /a\.dataset\.nav==='workbench'/);
});

test('P-002: shell declares the fixed seven-task navigation', () => {
  assert.match(shell, /id: 'workbench'.*?'工作台'/s);
  assert.match(shell, /'项目概览'/, 'overview');
  assert.match(shell, /'趋势与任务'/, 'trends');
  assert.match(shell, /'PR 与批次'/, 'records');
  assert.match(shell, /'数据质量'/, 'quality');
  assert.match(shell, /'数据与采集'/, 'collection');
  assert.match(shell, /'指标说明'/, 'metrics');
});

test('P-009: units.js loads before triton-view and Triton durations unify to minutes', () => {
  const scripts = [...html.matchAll(/<script src="([^"]+)" defer>/g)].map(m => m[1]);
  const idx = name => scripts.indexOf(name);
  assert.ok(idx('units.js') > idx('core.js'), 'units after core');
  assert.ok(idx('triton-view.js') > idx('units.js'), 'triton-view after units');
  assert.match(tritonView, /const dur = value => Units\.minutes\(value == null \? null : value \* 1000\)/);
});