const { test } = require('node:test');
const assert = require('node:assert/strict');
const { selectWindow, windowForHours, moveWindow, spreadPoints, chartStats, filterBranches, dashboardStats, circleMark, validDuration, startSourceLabel } = require('../web/triton-core.js');
const fs = require('node:fs');
const path = require('node:path');

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
const { isSlow, attentionGroups, freshnessSlots, matchesQuery, sameSessionMount, recoverWindow } = require('../web/triton-core.js');

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

/* ---- REQ-017: unified duration validity (finite, non-negative raw numbers) ---- */

test('validDuration accepts only finite non-negative raw numbers', () => {
  assert.equal(validDuration(0), true, 'a real zero is a valid duration');
  assert.equal(validDuration(600), true);
  for (const invalid of [null, undefined, '', '300', '-1', '0', NaN, Infinity, -Infinity, -1, false, true]) {
    assert.equal(validDuration(invalid), false, `${String(invalid)} must never become an implicit 0`);
  }
});

test('REQ-017 AC01: null, empty-string and negative durations yield zero valid completions', () => {
  const stats = chartStats([
    { status: 'success', duration_seconds: null },
    { status: 'failure', duration_seconds: '' },
    { status: 'success', duration_seconds: -1 },
  ]);
  assert.equal(stats.count, 0);
  assert.equal(stats.average, null);
  assert.equal(stats.p50, null);
  assert.equal(stats.p90, null);
  assert.equal(stats.max, 300, 'no valid observed values keeps the readable default scale');
});

test('REQ-017 AC02/AC03: real zero stays valid; mixed samples use only valid values', () => {
  const stats = chartStats([
    { status: 'success', duration_seconds: 0 },
    { status: 'success', duration_seconds: 600 },
    { status: 'failure', duration_seconds: '900' },
    { status: 'success', duration_seconds: -5 },
    { status: 'running', duration_seconds: 1200 },
    { status: 'cancelled', duration_seconds: null },
  ]);
  assert.equal(stats.count, 2);
  assert.equal(stats.average, 300);
  assert.equal(stats.p50, 300);
  assert.equal(stats.p90, 540);
  assert.equal(stats.max, 1200, 'valid observed values across statuses set the y-axis scale');
});

test('REQ-017: dashboardStats applies the same validity to the page-level summary', () => {
  const summary = dashboardStats([
    { pr: 1, status: 'success', duration_seconds: 600, missing: [] },
    { pr: 2, status: 'failure', duration_seconds: null, missing: [] },
    { pr: 3, status: 'success', duration_seconds: -1, missing: [] },
    { pr: 4, status: 'running', duration_seconds: 900, missing: [] },
  ]);
  assert.equal(summary.prs, 4);
  assert.equal(summary.batches, 4);
  assert.equal(summary.valid, 1);
  assert.equal(summary.median, 600);
});

test('REQ-017: isSlow and the small-sample fallback use only valid durations', () => {
  assert.equal(isSlow({ duration_seconds: -1, status: 'success' }, 100), false);
  assert.equal(isSlow({ duration_seconds: '4000', status: 'success' }, 100), false);
  const rows = [];
  for (let i = 1; i <= 9; i++) rows.push({ pr: i, status: 'success', duration_seconds: i * 100, start_at: '2026-10-08T01:00:00Z' });
  rows.push({ pr: 10, status: 'success', duration_seconds: null, start_at: '2026-10-08T02:00:00Z' });
  rows.push({ pr: 11, status: 'failure', duration_seconds: -9, start_at: '2026-10-08T03:00:00Z' });
  const groups = attentionGroups(rows, 850);
  assert.equal(groups[0].label, '耗时最长', 'invalid rows must not push the valid count to 10');
  assert.equal(groups[0].rows.length, 5);
  assert.ok(groups[0].rows.every(row => typeof row.duration_seconds === 'number' && row.duration_seconds >= 0));
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

/* ---- REQ-001: page-level set G (branch × shared time window) ---- */

test('page-level set G composes branch and time-window predicates with inclusive bounds', () => {
  const rows = [
    { pr: 1, base_branch: 'main', start_at: '2026-10-08T18:00:00Z', status: 'success', duration_seconds: 600 },
    { pr: 2, base_branch: 'main', start_at: '2026-10-08T22:00:00Z', status: 'failure', duration_seconds: 1200 },
    { pr: 3, base_branch: 'main-dev', start_at: '2026-10-08T23:30:00Z', status: 'running', duration_seconds: 900 },
    { pr: 4, base_branch: 'main', start_at: '2026-10-07T10:00:00Z', status: 'success', duration_seconds: 300 },
  ];
  const start = +new Date('2026-10-08T18:00:00Z');
  const end = +new Date('2026-10-08T23:30:00Z');
  const G = selected => selectWindow(filterBranches(rows, selected), start, end);
  assert.deepEqual(G(new Set()).map(r => r.pr), [1, 2, 3], 'batches whose start_at hits either boundary belong to G');
  assert.deepEqual(G(new Set(['main'])).map(r => r.pr), [1, 2], 'the branch predicate applies inside the shared window');
  assert.deepEqual(G(new Set(['main', 'main-dev'])).map(r => r.pr), [1, 2, 3], 'multi-branch selection unions within the window');
  assert.deepEqual(G(new Set(['release/x'])).map(r => r.pr), [], 'a branch without batches in the window yields an empty G');
});

test('an empty page-level set G yields a zeroed summary without falling back to the full snapshot', () => {
  const rows = [
    { pr: 1, base_branch: 'main', start_at: '2026-10-08T18:00:00Z', status: 'success', duration_seconds: 600 },
    { pr: 2, base_branch: 'main-dev', start_at: '2026-10-08T22:00:00Z', status: 'failure', duration_seconds: 1200 },
  ];
  const start = +new Date('2026-10-08T18:00:00Z');
  const end = +new Date('2026-10-08T23:30:00Z');
  const empty = dashboardStats(selectWindow(filterBranches(rows, new Set(['release/x'])), start, end));
  assert.equal(empty.batches, 0);
  assert.equal(empty.prs, 0);
  assert.equal(empty.valid, 0);
  assert.equal(empty.median, null, 'empty G must not invent duration samples');
  assert.equal(empty.p90, null, 'empty G must not invent a threshold');
  assert.equal(empty.incomplete, 0);
  assert.equal(empty.approximate, 0);
});

/* ---- REQ-002: slow threshold from the page-level set G ---- */

test('single valid sample yields P90 equal to the sample; zero valid keeps threshold null', () => {
  const single = dashboardStats([{ pr: 1, status: 'failure', duration_seconds: 290 }]);
  assert.equal(single.valid, 1);
  assert.equal(single.p90, 290, 'single-sample P90 equals the sample value');
  const runningOnly = dashboardStats([{ pr: 2, status: 'running', duration_seconds: 120 }]);
  assert.equal(runningOnly.valid, 0);
  assert.equal(runningOnly.p90, null, 'no valid completed samples means no threshold, never zero');
  assert.equal(isSlow({ duration_seconds: 120, status: 'running' }, runningOnly.p90), false);
});

test('chart-local stats and the page-level threshold are distinct computations', () => {
  const rows = [
    { pr: 1, status: 'success', duration_seconds: 600 },
    { pr: 2, status: 'failure', duration_seconds: 1200 },
    { pr: 3, status: 'failure', duration_seconds: 300 },
  ];
  assert.equal(dashboardStats(rows).p90, 1080, 'page-level P90 covers all completed batches in G');
  assert.equal(chartStats(rows.filter(r => r.status === 'failure')).p90, 1110, 'chart-local P90 covers only locally filtered batches');
});

/* ---- REQ-003: the shared list/CSV search predicate ---- */

test('matchesQuery: shared predicate for the list and CSV export scope', () => {
  const b = { pr: 2475, title: 'Bump actions/download-artifact from 4 to 7' };
  assert.equal(matchesQuery(b, ''), true, 'empty query matches every batch');
  assert.equal(matchesQuery(b, '   '), true, 'whitespace-only query matches every batch');
  assert.equal(matchesQuery(b, '2475'), true, 'PR number substring matches');
  assert.equal(matchesQuery(b, ' 2475 '), true, 'the query is trimmed before matching');
  assert.equal(matchesQuery(b, 'download-artifact'), true, 'title substring matches');
  assert.equal(matchesQuery(b, 'DOWNLOAD'), true, 'title matching is case-insensitive');
  assert.equal(matchesQuery({ pr: 1 }, 'xyz'), false, 'missing title does not throw and does not match');
  assert.equal(matchesQuery({ title: 'x' }, '24'), false, 'missing pr does not throw and does not match');
  assert.equal(matchesQuery(b, 'nonexistent'), false);
});

test('REQ-003: export scope is the page-level set G filtered by the list search', () => {
  const rows = [
    { pr: 1, base_branch: 'main', start_at: '2026-10-08T20:00:00Z', title: 'alpha first push' },
    { pr: 1, base_branch: 'main', start_at: '2026-10-08T21:00:00Z', title: 'alpha second push' },
    { pr: 2, base_branch: 'main-dev', start_at: '2026-10-08T22:00:00Z', title: 'beta' },
    { pr: 3, base_branch: 'main', start_at: '2026-10-07T10:00:00Z', title: 'gamma outside window' },
  ];
  const start = +new Date('2026-10-08T18:00:00Z');
  const end = +new Date('2026-10-09T00:00:00Z');
  const exportScope = (selected, query) => selectWindow(filterBranches(rows, selected), start, end)
    .filter(b => matchesQuery(b, query));
  assert.deepEqual(exportScope(new Set(), '').map(b => b.title), ['alpha first push', 'alpha second push', 'beta'],
    'no search: full G with both batches of PR1 retained separately');
  assert.deepEqual(exportScope(new Set(), 'alpha').map(b => b.title), ['alpha first push', 'alpha second push'],
    'different batches of the same PR are each retained under search');
  assert.deepEqual(exportScope(new Set(['main']), '').map(b => b.title), ['alpha first push', 'alpha second push'],
    'branch predicate composes with the time window');
  assert.deepEqual(exportScope(new Set(), 'gamma'), [], 'batches outside the time window never enter the export');
});

/* ---- REQ-004: in-session remount guard for the Triton view ---- */

test('sameSessionMount: skip remount only for the same live payload/container pair', () => {
  const payload = { batches: [] };
  const container = { isConnected: true, children: [{}] };
  assert.equal(sameSessionMount({ payload, container }, payload, container), true, 'same payload and live container → keep session');
  assert.equal(sameSessionMount({ payload, container }, { batches: [] }, container), false, 'reloaded payload object → remount');
  assert.equal(sameSessionMount({ payload, container }, payload, { isConnected: true, children: [{}] }), false, 'different container → remount');
  assert.equal(sameSessionMount({ payload, container }, payload, { isConnected: false, children: [{}] }), false, 'detached container → remount');
  assert.equal(sameSessionMount({ payload, container }, payload, { isConnected: true, children: [] }), false, 'emptied container → remount');
  assert.equal(sameSessionMount(null, payload, container), false, 'nothing mounted yet → mount');
});

/* ---- REQ-006: selection recovery against a new collection window ---- */

test('recoverWindow: intersection, full-coverage and end-anchored recovery rules', () => {
  const H = 3600000, MIN = 60000;
  const ns = 0, ne = 72 * H;
  const kept = recoverWindow(60 * H, 72 * H, ns, ne);
  assert.equal(kept.adjusted, false, 'an old selection fully inside the new window keeps its exact bounds');
  assert.equal(kept.reason, null);
  assert.equal(kept.start, 60 * H);
  assert.equal(kept.end, 72 * H);

  const clipped = recoverWindow(70 * H, 80 * H, ns, ne);
  assert.equal(clipped.adjusted, true, 'overlap above m is clipped to the intersection');
  assert.equal(clipped.start, 70 * H);
  assert.equal(clipped.end, 72 * H);

  const swallowed = recoverWindow(-10 * H, 100 * H, ns, ne);
  assert.equal(swallowed.start, ns, 'an old selection covering the whole new window clips to the new window');
  assert.equal(swallowed.end, ne);
  assert.equal(swallowed.adjusted, true);

  const noOverlap = recoverWindow(-10 * H, -2 * H, ns, ne);
  assert.equal(noOverlap.adjusted, true, 'no overlap recovers an end-anchored window of length L');
  assert.equal(noOverlap.start, 72 * H - 8 * H);
  assert.equal(noOverlap.end, 72 * H);

  const tinyOverlap = recoverWindow(-20 * MIN, 20 * MIN, ns, ne);
  assert.equal(tinyOverlap.start, 72 * H - 40 * MIN, 'overlap below m falls back to L = max(old span, m)');
  assert.equal(tinyOverlap.end, 72 * H);

  const shortOld = recoverWindow(10 * H, 10 * H + 10 * MIN, ns, ne);
  assert.equal(shortOld.end - shortOld.start, 30 * MIN, 'an old selection shorter than m is extended to m');
  assert.equal(shortOld.end, 72 * H);
});

test('recoverWindow: invalid old selections and degenerate new windows', () => {
  const H = 3600000;
  assert.equal(recoverWindow(0, H, H, H - 1), null, 'an invalid new window means a read failure');
  assert.equal(recoverWindow(0, H, NaN, H), null);
  const noOld = recoverWindow(NaN, NaN, 0, 20 * H);
  assert.equal(noOld.adjusted, false, 'no valid old selection falls back to the full new window');
  assert.equal(noOld.start, 0);
  assert.equal(noOld.end, 20 * H);
  const reversed = recoverWindow(H, 0, 0, 20 * H);
  assert.equal(reversed.start, 0, 'a reversed old selection is treated as absent');
  assert.equal(reversed.end, 20 * H);
  const tinyDomain = recoverWindow(5 * H, 15 * H, 0, 20 * 60000);
  assert.equal(tinyDomain.start, 0, 'a new window under 30 minutes always recovers its full span');
  assert.equal(tinyDomain.end, 20 * 60000);
});

test('REQ-014 AC02/AC04: startSourceLabel reports the start source and approximate flag', () => {
  assert.equal(startSourceLabel({ start_source: 'trigger_event', approximate: false }), '触发事件');
  assert.equal(startSourceLabel({ start_source: 'attempt_start', approximate: true }), '本次重跑开始，近似');
  assert.equal(startSourceLabel({ start_source: 'workflow_created', approximate: true }), '最早 workflow 创建，近似');
  assert.equal(startSourceLabel({ start_source: null }), '无起点证据');
  assert.equal(startSourceLabel({}), '无起点证据');
  assert.equal(startSourceLabel(null), '无起点证据');
  assert.equal(startSourceLabel({ start_source: 'unknown_source', approximate: false }), 'unknown_source');
});

test('REQ-046 AC01: both charts recompute selection stats over the frozen audit snapshot', () => {
  const freeze = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/triton-audit-freeze.json'), 'utf8'));
  const e2e = chartStats(freeze.batches);
  assert.equal(e2e.count, 65, '65 completion samples of 66 batches');
  assert.ok(Math.abs(e2e.p50 - 1580) < 1e-9);
  assert.ok(Math.abs(e2e.p90 - 3620.2000000000003) < 1e-9);
  assert.ok(Math.abs(e2e.average - 2129.5846153846155) < 1e-9);
  const page = dashboardStats(freeze.batches);
  assert.equal(page.prs, 38);
  assert.equal(page.batches, 66);
  assert.equal(page.valid, 65);
  assert.ok(Math.abs(page.median - 1580) < 1e-9);
  assert.ok(Math.abs(page.p90 - 3620.2000000000003) < 1e-9);
  assert.equal(page.approximate, 66);
  assert.equal(page.incomplete, 0);
  // The NPU chart maps npu_queue_seconds through the same chartStats contract
  // (web/triton-view.js drawNpu) over its applicable set of 48 points.
  const npuRows = freeze.batches.filter(b => validDuration(b.npu_queue_seconds));
  assert.equal(npuRows.length, 48);
  const npu = chartStats(npuRows.map(b => ({ ...b, duration_seconds: b.npu_queue_seconds })));
  assert.equal(npu.count, 48);
  assert.ok(Math.abs(npu.p50 - 56) < 1e-9);
  assert.ok(Math.abs(npu.p90 - 248.10000000000045) < 1e-9);
  assert.ok(Math.abs(npu.average - 109.52083333333333) < 1e-9);
});

test('REQ-046 AC04: a single sample expresses itself in every statistic', () => {
  const stats = chartStats([{ status: 'success', duration_seconds: 2122 }]);
  assert.equal(stats.count, 1);
  assert.equal(stats.average, 2122);
  assert.equal(stats.p50, 2122);
  assert.equal(stats.p90, 2122);
});
