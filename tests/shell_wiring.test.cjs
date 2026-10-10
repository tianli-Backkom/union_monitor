const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const shell = fs.readFileSync(path.join(__dirname, '..', 'web', 'shell.js'), 'utf8');

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

test('P-002: shell declares the fixed seven-task navigation', () => {
  assert.match(shell, /id: 'workbench'.*?'工作台'/s);
  assert.match(shell, /'项目概览'/, 'overview');
  assert.match(shell, /'趋势与任务'/, 'trends');
  assert.match(shell, /'PR 与批次'/, 'records');
  assert.match(shell, /'数据质量'/, 'quality');
  assert.match(shell, /'数据与采集'/, 'collection');
  assert.match(shell, /'指标说明'/, 'metrics');
});