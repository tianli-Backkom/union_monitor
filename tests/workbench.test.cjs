const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Workbench = require('../web/workbench.js');

const catalog = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'catalog.json'), 'utf8'));

test('projectCards enumerates only enabled projects', () => {
  const cards = Workbench.projectCards(catalog, {});
  assert.deepEqual(cards.map(c => c.project_id), ['ubs', 'triton']);
});

test('projectCards derives scope and capability facts from the catalog', () => {
  const cards = Workbench.projectCards(catalog, {});
  const ubs = cards.find(c => c.project_id === 'ubs');
  assert.equal(ubs.repository_count, 9);
  assert.equal(ubs.window_hours, 720);
  assert.equal(ubs.time_basis, 'pr_created_at');
  const triton = cards.find(c => c.project_id === 'triton');
  assert.equal(triton.repository_count, 1);
  assert.equal(triton.window_hours, 72);
});

test('unavailable projects show status, not a zero concern count', () => {
  const cards = Workbench.projectCards(catalog, { ubs: { data_mode: 'unavailable', task_status: 'failed' } });
  const ubs = cards.find(c => c.project_id === 'ubs');
  assert.equal(ubs.available, false);
  assert.equal(ubs.concern_count, null);
  assert.equal(ubs.data_mode_label, '不可用');
});

test('a fresh project with zero concerns is a real zero', () => {
  const cards = Workbench.projectCards(catalog, { ubs: { data_mode: 'fresh', task_status: 'success', concerns: [] } });
  const ubs = cards.find(c => c.project_id === 'ubs');
  assert.equal(ubs.available, true);
  assert.equal(ubs.concern_count, 0);
});

test('countConcernsByBatch dedupes by stable batch identity', () => {
  const concerns = [
    { batch_id: 'run:1:attempt:1', reason: '失败' },
    { batch_id: 'run:1:attempt:1', reason: '偏长' },
    { batch_id: 'run:2:attempt:1', reason: '失败' },
    { batch_id: '' },
    { reason: 'no id' },
  ];
  assert.equal(Workbench.countConcernsByBatch(concerns), 2);
  assert.equal(Workbench.countConcernsByBatch(null), null);
});

test('status labels cover task and data modes', () => {
  assert.equal(Workbench.taskLabel('success'), '成功');
  assert.equal(Workbench.taskLabel('cancelled'), '取消');
  assert.equal(Workbench.modeLabel('fresh'), '新数据');
  assert.equal(Workbench.modeLabel('fallback'), '回退');
});

test('P-013: the card keeps the three axes separate (execution/evidence/time)', () => {
  const status = {
    task_status: 'failed',
    data_mode: 'fallback',
    collected_at: '2026-10-09T23:30:00Z',
    validation_status: 'passed',
    snapshot_version: 'rel-1',
  };
  const card = Workbench.projectCard(catalog.projects[0], status, {
    published_at: '2026-10-10T08:00:00Z',
    schedule_time: '2026-10-10T07:30:00Z',
  });
  assert.equal(card.task_status, 'failed');       // execution stays failed
  assert.equal(card.data_mode, 'fallback');       // evidence/version stays fallback
  assert.equal(card.collected_at, '2026-10-09T23:30:00Z'); // time stays the OLD collection
  assert.equal(card.validation_status, 'passed');
  assert.equal(card.delayed, true);               // publish later than schedule = observation
});

test('P-013: delayed is null without a schedule, and never re-writes collected_at', () => {
  const card = Workbench.projectCard(catalog.projects[0], { data_mode: 'fresh', collected_at: '2026-10-10T00:00:00Z' }, { published_at: '2026-10-10T08:00:00Z' });
  assert.equal(card.delayed, null);
  assert.equal(card.collected_at, '2026-10-10T00:00:00Z');
});