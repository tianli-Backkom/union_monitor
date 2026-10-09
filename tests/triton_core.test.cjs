const { test } = require('node:test');
const assert = require('node:assert/strict');
const { selectWindow, windowForHours, moveWindow, spreadPoints, chartStats, filterBranches, dashboardStats, circleMark } = require('../web/triton-core.js');

test('selectWindow keeps the lower boundary of the requested range', () => {
  const rows = [
    { start_at: '2026-09-23T11:59:59Z' },
    { start_at: '2026-09-23T12:00:00Z' },
    { start_at: '2026-09-23T23:00:00Z' },
  ];
  const selected = selectWindow(rows, +new Date('2026-09-23T12:00:00Z'), +new Date('2026-09-24T00:00:00Z'));
  assert.deepEqual(selected, rows.slice(1), '12-hour range should include its lower boundary');
});

test('windowForHours and moveWindow clamp against the domain', () => {
  const domainStart = +new Date('2026-09-21T00:00:00Z');
  const domainEnd = +new Date('2026-09-24T00:00:00Z');
  assert.deepEqual(windowForHours(domainStart, domainEnd, 24), [domainEnd - 86400000, domainEnd]);
  assert.deepEqual(moveWindow(domainStart, domainEnd, domainEnd - 86400000, domainEnd, -43200000), [domainEnd - 129600000, domainEnd - 43200000]);
  assert.deepEqual(moveWindow(domainStart, domainEnd, domainStart, domainStart + 86400000, -43200000), [domainStart, domainStart + 86400000]);
});

test('spreadPoints offsets overlapping marks and stays inside the plot bounds', () => {
  const spread = spreadPoints([{x:10,y:10},{x:11,y:11},{x:40,y:40}], 4);
  assert.deepEqual(spread[0], {x:10,y:10});
  assert.notDeepEqual(spread[1], {x:11,y:11}, 'overlapping marks should receive a small visual offset');
  assert.deepEqual(spread[2], {x:40,y:40});
  const bounded = spreadPoints([{x:10,y:100},{x:10,y:100},{x:10,y:100}], 12, { minX: 0, maxX: 100, minY: 10, maxY: 100 });
  assert.ok(bounded.every(point => point.y >= 10 && point.y <= 100), 'spread marks must stay inside the plot baseline');
});

test('chartStats measures completed batches and keeps a readable empty scale', () => {
  const stats = chartStats([
    { duration_seconds: 600, status: 'success' },
    { duration_seconds: 900, status: 'failure' },
    { duration_seconds: 1200, status: 'cancelled' },
  ]);
  assert.equal(stats.max, 1200, 'selected points should determine the y-axis maximum');
  assert.equal(stats.p90, 870, 'selected completed points should determine the chart P90');
  assert.equal(stats.average, 750, 'average should only use completed batches');
  assert.equal(stats.p50, 750, 'P50 should only use completed batches');
  assert.equal(stats.count, 2, 'sample count should only include completed batches');
  assert.equal(chartStats([]).max, 300, 'empty ranges should keep a small readable scale');
  assert.equal(chartStats([]).average, null, 'empty ranges should not invent an average');
});

test('filterBranches and dashboardStats aggregate branch-filtered rows', () => {
  const branchRows = [
    { pr: 1, base_branch: 'main', status: 'success', duration_seconds: 600, missing: [] },
    { pr: 2, base_branch: 'main-dev', status: 'failure', duration_seconds: 1200, missing: ['gap'] },
    { pr: 1, base_branch: 'release/3.2.2', status: 'running', duration_seconds: 300, missing: [] },
  ];
  assert.deepEqual(filterBranches(branchRows, new Set(['main', 'release/3.2.2'])), [branchRows[0], branchRows[2]]);
  assert.deepEqual(filterBranches(branchRows, new Set()), branchRows, 'empty selection means all branches');
  const summary = dashboardStats(branchRows.slice(0, 2));
  assert.equal(summary.prs, 2);
  assert.equal(summary.batches, 2);
  assert.equal(summary.valid, 2);
  assert.equal(summary.median, 900);
  assert.equal(summary.incomplete, 1);
});

test('circleMark renders solid circles with a larger hit area', () => {
  const mark = circleMark({ status: 'running' }, 42, 21, 7, '#356ea8');
  assert.match(mark, /^<g class="mark-hit"/, 'marks need a larger pointer hit area');
  assert.match(mark, /<circle class="dot"/, 'running marks must use circles');
  assert.match(mark, /fill="#356ea8"/, 'marks must be solid status colors');
  assert.doesNotMatch(mark, /<path|fill="none"/, 'marks must not use triangles or hollow shapes');
});

/* ---- T8 additions: pure helpers for the merged Triton view ---- */
const { isSlow, attentionGroups, freshnessSlots } = require('../web/triton-core.js');

test('isSlow flags completed batches at or beyond P90 and excludes running ones', () => {
  assert.equal(isSlow({ duration_seconds: 4000, status: 'success' }, 3620), true);
  assert.equal(isSlow({ duration_seconds: 3620, status: 'failure' }, 3620), true, 'boundary values count as slow');
  assert.equal(isSlow({ duration_seconds: 100, status: 'success' }, 3620), false);
  assert.equal(isSlow({ duration_seconds: 90000, status: 'running' }, 3620), false, 'running batches are never slow');
  assert.equal(isSlow({ duration_seconds: 4000, status: 'cancelled' }, 3620), true, 'cancelled batches with observed time can be slow');
  assert.equal(isSlow({ duration_seconds: null, status: 'success' }, 3620), false);
  assert.equal(isSlow({ status: 'success' }, 3620), false, 'missing duration is never slow');
  assert.equal(isSlow({ duration_seconds: 4000, status: 'success' }, null), false, 'without a P90 nothing is slow');
});

test('attentionGroups falls back to longest completed runs when valid samples are scarce', () => {
  const rows = [
    { pr: 1, status: 'success', duration_seconds: 5000, start_at: '2026-10-08T01:00:00Z' },
    { pr: 2, status: 'success', duration_seconds: 900, start_at: '2026-10-08T02:00:00Z' },
    { pr: 3, status: 'failure', duration_seconds: 4200, start_at: '2026-10-08T05:00:00Z' },
    { pr: 4, status: 'failure', duration_seconds: 800, start_at: '2026-10-08T03:00:00Z' },
    { pr: 5, status: 'running', duration_seconds: 1200, start_at: '2026-10-08T06:00:00Z' },
    { pr: 6, status: 'running', duration_seconds: 300, start_at: '2026-10-08T04:00:00Z' },
    { pr: 7, status: 'cancelled', duration_seconds: 3600, start_at: '2026-10-08T07:00:00Z' },
  ];
  const groups = attentionGroups(rows, 3600);
  assert.deepEqual(groups.map(group => group.key), ['slow', 'running', 'failure']);
  assert.equal(groups[0].label, '耗时最长', 'fewer than 10 valid samples shows the longest completed runs');
  assert.deepEqual(groups[0].rows.map(row => row.pr), [1, 3, 2, 4], 'fallback sorts completed batches by duration descending');
  assert.deepEqual(groups[1].rows.map(row => row.pr), [5, 6], 'running group sorts by observed duration descending');
  assert.deepEqual(groups[2].rows.map(row => row.pr), [4, 3], 'failure group sorts by start time ascending');
});

test('attentionGroups keeps the P90 slow group once samples are sufficient', () => {
  const rows = [];
  for (let i = 1; i <= 12; i++) rows.push({ pr: i, status: 'success', duration_seconds: i * 100, start_at: `2026-10-08T0${i % 10}:00:00Z` });
  rows.push({ pr: 99, status: 'running', duration_seconds: 9900, start_at: '2026-10-08T08:00:00Z' });
  rows.push({ pr: 98, status: 'failure', duration_seconds: 500, start_at: '2026-10-07T09:00:00Z' });
  const groups = attentionGroups(rows, 1100);
  assert.equal(groups[0].label, '耗时偏长');
  assert.deepEqual(groups[0].rows.map(row => row.pr), [12, 11], 'slow group holds batches at or beyond P90, longest first');
  assert.deepEqual(groups[1].rows.map(row => row.pr), [99]);
  assert.deepEqual(groups[2].rows.map(row => row.pr), [98]);
});

test('attentionGroups tolerates empty input', () => {
  const groups = attentionGroups([], 1000);
  assert.deepEqual(groups.map(group => [group.key, group.rows.length]), [['slow', 0], ['running', 0], ['failure', 0]]);
  assert.equal(groups[0].label, '耗时最长');
});

test('freshnessSlots finds the latest grace-elapsed Beijing slot', () => {
  // 2026-10-09 21:35 Beijing == 13:35 UTC: the 20:00 slot's 90-minute grace has elapsed.
  const now = Date.UTC(2026, 9, 9, 13, 35);
  const result = freshnessSlots(now, Date.UTC(2026, 9, 9, 11, 0));
  assert.equal(result.slots.length, 5);
  assert.equal(result.latest, Date.UTC(2026, 9, 9, 12, 0), 'latest slot is Beijing 20:00');
  assert.equal(result.stale, true, 'collection before the latest slot is stale');
  assert.equal(freshnessSlots(now, Date.UTC(2026, 9, 9, 12, 30)).stale, false, 'collection after the latest slot is fresh');
  assert.equal(freshnessSlots(now, '2026-10-09T11:00:00Z').stale, true, 'ISO collection timestamps are accepted');
});

test('freshnessSlots respects the grace window and the early-morning fallback', () => {
  // 21:20 Beijing: the 20:00 slot is still inside its 90-minute grace period.
  const evening = Date.UTC(2026, 9, 9, 13, 20);
  const grace = freshnessSlots(evening, Date.UTC(2026, 9, 9, 10, 30));
  assert.equal(grace.latest, Date.UTC(2026, 9, 9, 10, 0), 'grace not elapsed: latest is Beijing 18:00');
  assert.equal(grace.stale, false, 'collected after the 18:00 slot is still fresh');
  assert.equal(freshnessSlots(evening, Date.UTC(2026, 9, 9, 9, 59)).stale, true, 'missing the 18:00 slot is stale');
  // 07:00 Beijing == 2026-10-08 23:00 UTC: only yesterday's 20:00 slot has fully passed.
  const morning = Date.UTC(2026, 9, 8, 23, 0);
  const early = freshnessSlots(morning, Date.UTC(2026, 9, 8, 11, 0));
  assert.equal(early.slots[0], Date.UTC(2026, 9, 8, 12, 0), 'first slot is yesterday 20:00 Beijing');
  assert.equal(early.latest, Date.UTC(2026, 9, 8, 12, 0));
  assert.equal(early.stale, true, 'missing yesterday evening run is stale in the morning');
  assert.equal(freshnessSlots(morning, Date.UTC(2026, 9, 8, 12, 0)).stale, false, 'collecting exactly at the slot counts as fresh');
});
