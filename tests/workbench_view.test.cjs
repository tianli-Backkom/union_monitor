const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// workbench-view.js reads root.Workbench/root.Shell at call time.
globalThis.QueryState = require('../web/query-state.js');
globalThis.Workbench = require('../web/workbench.js');
globalThis.Shell = require('../web/shell.js');
const View = require('../web/workbench-view.js');

const catalog = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'catalog.json'), 'utf8'));

test('P-001: workbench cards render each enabled project with status, not fake zero', () => {
  const html = View.cardsHTML(catalog, { ubs: { data_mode: 'unavailable', task_status: 'failed' } });
  assert.match(html, /openEuler UBS/);
  assert.match(html, /Triton-Ascend/);
  assert.match(html, /不可用/);
  assert.match(html, /9 仓/);
  assert.match(html, /1 仓/);
});

test('P-001: concern table dedupes by batch and keeps a source link', () => {
  const rows = [
    { project_id: 'ubs', repository_id: 'gitcode:openeuler/ubs-engine', batch_id: 'run:1:attempt:1', reasons: ['失败', '偏长'], source_url: 'https://ci/x/1' },
  ];
  const html = View.concernTableHTML(rows);
  assert.match(html, /失败、偏长/);
  assert.match(html, /run:1:attempt:1/);
  assert.match(html, /<a href="https:\/\/ci\/x\/1"/);
  assert.match(View.concernTableHTML([]), /当前没有需要关注的记录/);
});

test('P-002: project selector lists all projects and marks the active one', () => {
  const html = View.projectSelectorHTML(catalog, 'triton');
  assert.match(html, /全部项目/);
  assert.match(html, /value="ubs"/);
  assert.match(html, /value="triton" selected/);
});

test('esc neutralizes HTML characters', () => {
  assert.equal(View.esc('<b>"x"&'), '&lt;b&gt;&quot;x&quot;&amp;');
});