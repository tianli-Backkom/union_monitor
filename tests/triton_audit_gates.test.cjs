const { test } = require('node:test');
const assert = require('node:assert/strict');
const core = require('../web/triton-core.js');

test('unknown workflow observations do not lower commit E2E summaries or chart denominators', () => {
  const rows = [
    {id:'known',pr:7,status:'success',duration_seconds:600,missing:[]},
    {id:'unknown',pr:null,status:'failure',duration_seconds:10,missing:['未可靠关联 PR']},
  ];
  assert.equal(core.dashboardStats(rows).valid, 1);
  assert.equal(core.dashboardStats(rows).p90, 600);
  assert.equal(core.chartStats(rows).count, 1);
  assert.equal(core.chartStats(rows).p90, 600);
  assert.equal(core.chartStats(rows, 'npu').count, 2, 'NPU evidence has an independent sample predicate');
});

test('explicit E2E exclusions govern small-sample attention without deleting failure records', () => {
  const rows = [{id:'known',pr:7,status:'success',duration_seconds:600},
    {id:'unknown',pr:null,status:'failure',duration_seconds:99999,e2e_sample_eligible:false}];
  const groups = core.attentionGroups(rows, 600);
  assert.deepEqual(groups[0].rows.map(row=>row.id), ['known']);
  assert.deepEqual(groups[2].rows.map(row=>row.id), ['unknown']);
  assert.equal(core.isSlow(rows[1],600), false);
});

test('unresolved mark identity names its run rather than inventing a shared PR history', () => {
  const label = core.markLabel({pr:null,sha:'abc',e2e_index:276,e2e_total:276,workflows:[{id:123,attempt:2}]}, 'e2e');
  assert.match(label, /123/);
  assert.doesNotMatch(label, /PR #\?|276\/276/);
});

test('production noon and afternoon updates become stale only after their 90-minute grace', () => {
  assert.equal(core.freshnessSlots('2026-10-11T13:29:59+08:00', '2026-10-11T08:17:00+08:00').stale, false);
  assert.equal(core.freshnessSlots('2026-10-11T13:30:00+08:00', '2026-10-11T08:17:00+08:00').stale, true);
  assert.equal(core.freshnessSlots('2026-10-11T17:29:59+08:00', '2026-10-11T12:17:00+08:00').stale, false);
  assert.equal(core.freshnessSlots('2026-10-11T17:30:00+08:00', '2026-10-11T12:17:00+08:00').stale, true);
});
