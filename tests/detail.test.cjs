const { test } = require('node:test');
const assert = require('node:assert/strict');

const D = require('../web/detail.js');

function batch(url, number, end_ms, request_ms) {
  return { url, number, end_ms, request_ms, trigger: {}, children: [] };
}

test('P-007: lifecycle label is honest — unknown lifecycle is 未采集, not invented', () => {
  assert.equal(D.lifecycleLabel('open'), '开启中');
  assert.equal(D.lifecycleLabel('merged'), '已合入');
  assert.equal(D.lifecycleLabel('closed'), '已关闭未合入');
  assert.equal(D.lifecycleLabel(undefined), '未采集');
  assert.equal(D.lifecycleLabel(''), '未采集');
});

test('P-007: detail title names project / repository / PR#', () => {
  assert.equal(D.detailTitle('ubs', 'gitcode:openeuler/ubs-engine', 248), 'ubs / gitcode:openeuler/ubs-engine / PR #248');
});

test('P-007: entering from a batch row expands that selected batch', () => {
  const batches = [batch('t/3', 3, 3000), batch('t/1', 1, 1000), batch('t/2', 2, 2000)];
  const r = D.defaultExpandedBatch(batches, { entryId: 't/2', representativeUrl: 't/1' });
  assert.equal(r.batch.url, 't/2');
  assert.equal(r.reason, 'entry');
});

test('P-007: entering from a PR row expands its representative batch', () => {
  const batches = [batch('t/3', 3, 3000), batch('t/1', 1, 1000)];
  const r = D.defaultExpandedBatch(batches, { representativeUrl: 't/1' });
  assert.equal(r.batch.url, 't/1');
  assert.equal(r.reason, 'representative');
});

test('P-007: no representative chooses the latest collected batch with an explicit reason', () => {
  const batches = [batch('t/1', 1, 1000), batch('t/3', 3, 3000), batch('t/2', 2, 2500)];
  const r = D.defaultExpandedBatch(batches, {});
  assert.equal(r.batch.url, 't/3');
  assert.equal(r.reason, 'no-representative');
});

test('P-007: an empty detail never fabricates a representative', () => {
  const r = D.defaultExpandedBatch([], {});
  assert.equal(r.batch, null);
  assert.equal(r.reason, 'empty');
});

test('P-007: taskTimeline normalises trigger + children into one ordered list', () => {
  const b = {
    trigger: { kind: 'trigger', number: 7, url: 't/7', queue_ms: 0, duration_ms: 1000, result: 'SUCCESS' },
    children: [{ kind: 'x86', number: 12, url: 'j/12', queue_ms: 500, duration_ms: 2000, total_ms: 2500, result: 'SUCCESS' }],
  };
  const rows = D.taskTimeline(b);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].role, 'trigger');
  assert.equal(rows[1].role, 'task');
  assert.equal(rows[1].kind, 'x86');
  assert.equal(rows[1].wait_ms, 500);
  assert.equal(rows[1].total_ms, 2500);
});

test('P-007: evidenceLine carries version, collected time and boundary', () => {
  assert.equal(
    D.evidenceLine({ snapshot_version: 'rel-1', collected_at: '2026-10-09T23:30:00Z', boundary: '已采集记录，非平台完整历史' }),
    '数据版本 rel-1 · 采集时间 2026-10-09T23:30:00Z · 证据覆盖边界 已采集记录，非平台完整历史'
  );
});