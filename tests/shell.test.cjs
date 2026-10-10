const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// The shell's concernRows reads root.QueryState at call time; provide it.
globalThis.QueryState = require('../web/query-state.js');
const Shell = require('../web/shell.js');

const catalog = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'catalog.json'), 'utf8'));

test('P-002: fixed task navigation has the seven stable entries', () => {
  assert.deepEqual(Shell.FIXED_TASKS.map(t => t.id), [
    'workbench', 'overview', 'trends', 'records', 'quality', 'collection', 'metrics',
  ]);
  assert.equal(Shell.taskLabel('records'), 'PR 与批次');
  assert.equal(Shell.taskLabel('missing'), null);
});

test('P-002: repositoryChoices keeps the full source:owner/repo identity', () => {
  const choices = Shell.repositoryChoices(catalog, 'ubs');
  assert.equal(choices[0].id, 'all');
  assert.equal(choices[0].is_default, true); // multi-repo: default to "all"
  assert.equal(choices[1].label, 'gitcode:openeuler/ubs-engine');
  assert.equal(choices.length, 10); // all + 9 repos
});

test('P-002: a single-repository project auto-selects its only repo', () => {
  const choices = Shell.repositoryChoices(catalog, 'triton');
  assert.equal(choices.length, 2); // all + 1 repo
  assert.equal(choices[0].is_default, false);
  assert.equal(choices[1].is_default, true);
  assert.equal(Shell.defaultRepositoryId(catalog, 'triton'), 'github:triton-lang/triton-ascend');
  assert.equal(Shell.defaultRepositoryId(catalog, 'ubs'), null);
});

test('P-002: enabledProjects never branches on a hardcoded project id', () => {
  assert.deepEqual(Shell.enabledProjects(catalog).map(p => p.project_id), ['ubs', 'triton']);
});

test('P-005: concernRows dedupes by stable batch identity, not reason labels', () => {
  const concerns = [
    { project_id: 'ubs', repository_id: 'gitcode:openeuler/ubs-engine', batch_id: 'run:1:attempt:1', reason: '失败', source_url: 'https://ci/x/1' },
    { project_id: 'ubs', repository_id: 'gitcode:openeuler/ubs-engine', batch_id: 'run:1:attempt:1', reason: '偏长', source_url: 'https://ci/x/1' },
    { project_id: 'ubs', repository_id: 'gitcode:openeuler/ubs-engine', batch_id: 'run:2:attempt:1', reason: '失败', source_url: 'https://ci/x/2' },
    { project_id: 'ubs', repository_id: 'gitcode:openeuler/ubs-engine', batch_id: '', reason: 'no id', source_url: 'https://ci/x/3' },
  ];
  const rows = Shell.concernRows(concerns);
  assert.equal(rows.length, 2);
  const first = rows.find(r => r.batch_id === 'run:1:attempt:1');
  assert.deepEqual(first.reasons, ['失败', '偏长']);
  assert.equal(first.project_id, 'ubs');
  assert.equal(first.source_url, 'https://ci/x/1');
});