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

test('UDR-009-TC01: same-number PRs in different repositories stay separate rows', () => {
  const snapshots = {
    'ubs-engine': { meta: { repository: 'gitcode:openeuler/ubs-engine' }, prs: [{ number: 42, batches: [{ number: 3, status: 'failure', url: 'https://ci/a' }] }] },
    'ubs-comm': { meta: { repository: 'gitcode:openeuler/ubs-comm' }, prs: [{ number: 42, batches: [{ number: 3, status: 'failure', url: 'https://ci/b' }] }] },
  };
  const rows = Shell.concernRows(Shell.buildWorkbenchConcerns(snapshots, null));
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map(r => r.batch_id).sort(), [
    'gitcode:openeuler/ubs-comm#42::3',
    'gitcode:openeuler/ubs-engine#42::3',
  ]);
});

test('UDR-009-TC01: one batch with three reasons merges into one row of three labels', () => {
  // Triton batch: failure + unknown PR + slow (>= p90) -> three reasons.
  const triton = { batches: [
    { id: 'runA', status: 'failure', pr: null, duration_seconds: 500, action_url: 'https://gh/a' },
    { id: 'runB', status: 'success', pr: 7, duration_seconds: 10, action_url: 'https://gh/b' },
  ] };
  const concerns = Shell.buildWorkbenchConcerns({}, triton);
  const slow = concerns.filter(c => c.batch_id === 'github:triton-lang/triton-ascend#runA');
  assert.deepEqual(slow.map(c => c.reason).sort(), ['失败', '未知 PR 身份', '耗时偏长']);
  const rows = Shell.concernRows(concerns);
  const a = rows.find(r => r.batch_id === 'github:triton-lang/triton-ascend#runA');
  assert.equal(a.reasons.length, 3);
});

test('UDR-009-TC02: unknown-PR and collection errors keep an independent source identity', () => {
  const snapshots = { 'r': { meta: { repository: 'gitcode:openeuler/r', errors: [{ source: 'jenkins', reason: '连接超时' }] }, prs: [] } };
  const concerns = Shell.buildWorkbenchConcerns(snapshots, { batches: [{ id: 'u1', status: 'running', pr: null, duration_seconds: 3 }] });
  assert.ok(concerns.some(c => c.project_id === 'ubs' && c.batch_id === 'gitcode:openeuler/r::collection:jenkins'));
  assert.ok(concerns.some(c => c.project_id === 'triton' && c.reason === '未知 PR 身份'));
});