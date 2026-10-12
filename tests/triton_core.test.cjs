const { test } = require('node:test');
const assert = require('node:assert/strict');
const { selectWindow, windowForHours, moveWindow, spreadPoints, chartStats, filterBranches, dashboardStats, circleMark, markLabel, validDuration, startSourceLabel } = require('../web/triton-core.js');
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
const { isSlow, attentionGroups, attentionNote, rowDomIds, minWindowSpan, clampBoundary, keyWindow, navSliderSemantics, freshnessSlots, matchesQuery, sameSessionMount, recoverWindow, placeTipBox, axisTicks } = require('../web/triton-core.js');

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

/* ---- REQ-026: strategy from G, search only filters inside the groups ---- */

test('REQ-026 AC01: searching the frozen snapshot for PR2455 keeps the G strategy', () => {
  const freeze = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/triton-audit-freeze.json'), 'utf8'));
  const page = dashboardStats(freeze.batches);
  assert.equal(page.valid, 65);
  assert.equal(freeze.batches.filter(b => matchesQuery(b, '2455')).length, 1, 'the search narrows the list to a single batch');
  const unsearched = attentionGroups(freeze.batches, page.p90);
  assert.equal(unsearched[0].label, '耗时偏长');
  assert.equal(unsearched[0].rows.length, 8, 'the G-based P90 group holds the eight batches at or beyond P90');
  const groups = attentionGroups(freeze.batches, page.p90, '2455');
  assert.deepEqual(groups.map(group => [group.label, group.rows.length]), [['耗时偏长', 0], ['执行中', 0], ['失败', 1]],
    'a single search hit must not flip G to the top-5 耗时最长 strategy');
  assert.equal(groups[2].rows[0].pr, 2455, 'the matched failure batch lands in the failure group, not a slow group');
  assert.ok(groups[0].rows.every(b => matchesQuery(b, '2455') && isSlow(b, page.p90)));
  const note = attentionNote(page.valid);
  assert.ok(note.includes('65') && note.includes('P90'), 'the note keeps the G sample denominator');
});

test('REQ-026 AC02: 9 and 10 valid samples pick different strategies with the same denominator in the note', () => {
  const rowsFor = n => Array.from({ length: n }, (_, i) => ({ pr: i + 1, status: 'success', duration_seconds: (i + 1) * 100, start_at: '2026-10-08T01:00:00Z' }));
  const nine = attentionGroups(rowsFor(9), 850);
  assert.equal(nine[0].label, '耗时最长', '9 valid samples use the top-5 longest strategy');
  assert.deepEqual(nine[0].rows.map(row => row.pr), [9, 8, 7, 6, 5]);
  assert.ok(attentionNote(9).includes('页级范围 9 个'), 'the note names the 9-sample denominator');
  const tenRows = rowsFor(10);
  const tenPage = dashboardStats(tenRows);
  assert.equal(tenPage.valid, 10);
  const ten = attentionGroups(tenRows, tenPage.p90);
  assert.equal(ten[0].label, '耗时偏长', '10 valid samples use the P90 strategy');
  assert.deepEqual(ten[0].rows.map(row => row.pr), [10], 'the P90 group holds batches at or beyond the threshold');
  assert.ok(attentionNote(10).includes('页级范围 10 个'), 'the note names the 10-sample denominator');
});

test('REQ-026 AC03: search keeps group names and counts consistent; groups may overlap', () => {
  const rows = [];
  for (let i = 1; i <= 12; i++) rows.push({ pr: i, title: 'chore batch', status: 'success', duration_seconds: i * 100, start_at: '2026-10-08T01:00:00Z' });
  rows.push({ pr: 13, title: 'flaky gate', status: 'failure', duration_seconds: 1300, start_at: '2026-10-08T02:00:00Z' });
  rows.push({ pr: 14, title: 'chore batch', status: 'running', duration_seconds: 500, start_at: '2026-10-08T03:00:00Z' });
  const page = dashboardStats(rows);
  assert.equal(page.valid, 13);
  const all = attentionGroups(rows, page.p90, '');
  assert.deepEqual(all.map(group => group.label), ['耗时偏长', '执行中', '失败']);
  assert.deepEqual(all.map(group => group.rows.length), [2, 1, 1]);
  const overlapRow = all[0].rows.find(row => row.pr === 13);
  assert.ok(overlapRow, 'a failed batch beyond P90 stays in the slow group');
  assert.equal(all[2].rows[0], overlapRow, 'the same record also appears in the failure group');
  const shown = all.flatMap(group => group.rows);
  assert.ok(new Set(shown).size < shown.length, 'group counts must not be summed into a unique batch count');

  const zero = attentionGroups(rows, page.p90, 'zzz');
  assert.deepEqual(zero.map(group => group.label), ['耗时偏长', '执行中', '失败'], 'zero search hits keep the G-based group names');
  assert.deepEqual(zero.map(group => group.rows.length), [0, 0, 0]);

  const one = attentionGroups(rows, page.p90, 'flaky');
  assert.deepEqual(one.map(group => group.rows.length), [1, 0, 1], 'one searched record shows in every group it belongs to');

  const multi = attentionGroups(rows, page.p90, 'chore');
  assert.deepEqual(multi.map(group => group.rows.length), [1, 1, 0]);
  assert.ok(multi.every(group => group.rows.every(row => matchesQuery(row, 'chore'))), 'group counts match the records shown');
});

test('REQ-026 AC04: the CSV scope stays G × search even under the top-5 attention strategy', () => {
  const rows = Array.from({ length: 7 }, (_, i) => ({ pr: 101 + i, title: 'export probe', status: 'success', duration_seconds: (i + 1) * 100, start_at: '2026-10-08T01:00:00Z' }));
  const page = dashboardStats(rows);
  assert.equal(page.valid, 7, 'fewer than 10 valid samples: the attention list falls back to the top-5 longest');
  const groups = attentionGroups(rows, page.p90, 'export');
  assert.equal(groups[0].label, '耗时最长');
  assert.equal(groups[0].rows.length, 5, 'the attention list caps the highlighted slow group at five');
  const exportScope = rows.filter(b => matchesQuery(b, 'export'));
  assert.equal(exportScope.length, 7, 'the CSV still exports every searched batch of G, not just the highlighted five');
});

/* ---- REQ-027: keyboard-operable shared time range ---- */

test('REQ-027 AC01: keyWindow pans the window and reaches the domain edges', () => {
  const H = 3600000;
  const step = 24 * H / 10;
  assert.deepEqual(keyWindow('window-right', 0, 72 * H, 24 * H, 48 * H), [24 * H + step, 48 * H + step]);
  assert.deepEqual(keyWindow('window-left', 0, 72 * H, 24 * H, 48 * H), [24 * H - step, 48 * H - step]);
  assert.deepEqual(keyWindow('window-home', 0, 72 * H, 24 * H, 48 * H), [0, 24 * H]);
  assert.deepEqual(keyWindow('window-end', 0, 72 * H, 24 * H, 48 * H), [48 * H, 72 * H]);
  // panning into an edge clamps exactly like the pointer's moveWindow (AC04)
  assert.deepEqual(keyWindow('window-right', 0, 72 * H, 46 * H, 70 * H), [48 * H, 72 * H]);
  assert.deepEqual(keyWindow('window-right', 0, 72 * H, 46 * H, 70 * H), moveWindow(0, 72 * H, 46 * H, 70 * H, step));
  assert.deepEqual(keyWindow('window-left', 0, 72 * H, 2 * H, 26 * H), [0, 24 * H]);
  assert.deepEqual(keyWindow('window-left', 0, 72 * H, 2 * H, 26 * H), moveWindow(0, 72 * H, 2 * H, 26 * H, -step));
  assert.deepEqual(keyWindow('window-right', 0, 72 * H, 24 * H, 48 * H), moveWindow(0, 72 * H, 24 * H, 48 * H, step));
});

test('REQ-027 AC01/AC03: keyWindow adjusts boundaries with the 30-minute floor', () => {
  const H = 3600000, M = 60000;
  const step = 24 * H / 10;
  assert.deepEqual(keyWindow('start-right', 0, 72 * H, 24 * H, 48 * H), [24 * H + step, 48 * H]);
  assert.deepEqual(keyWindow('end-left', 0, 72 * H, 24 * H, 48 * H), [24 * H, 48 * H - step]);
  assert.deepEqual(keyWindow('start-home', 0, 72 * H, 24 * H, 48 * H), [0, 48 * H]);
  assert.deepEqual(keyWindow('start-end', 0, 72 * H, 24 * H, 48 * H), [48 * H - 30 * M, 48 * H]);
  assert.deepEqual(keyWindow('end-home', 0, 72 * H, 24 * H, 48 * H), [24 * H, 24 * H + 30 * M]);
  assert.deepEqual(keyWindow('end-end', 0, 72 * H, 24 * H, 48 * H), [24 * H, 72 * H]);
  // repeated start-right never crosses the 30-minute floor
  let window = [46 * H, 47 * H];
  for (let i = 0; i < 10; i++) window = keyWindow('start-right', 0, 72 * H, window[0], window[1]);
  assert.deepEqual(window, [47 * H - 30 * M, 47 * H], 'the start edge stops at end minus 30 minutes');
  // boundaries stay inside the collection window
  assert.deepEqual(keyWindow('start-left', 0, 72 * H, 30 * M, 60 * M), [0, 60 * M]);
  assert.deepEqual(keyWindow('end-right', 0, 72 * H, 70 * H, 71.75 * H), [70 * H, 72 * H], 'end clamps at the domain end');
});

test('REQ-027 AC03: a domain shorter than 30 minutes allows only the whole window', () => {
  const M = 60000;
  assert.deepEqual(keyWindow('start-right', 0, 20 * M, 0, 20 * M), [0, 20 * M], 'the start edge cannot leave the domain');
  assert.deepEqual(keyWindow('end-left', 0, 20 * M, 0, 20 * M), [0, 20 * M], 'the end edge cannot leave the domain');
  assert.deepEqual(keyWindow('window-right', 0, 20 * M, 0, 20 * M), [0, 20 * M]);
  assert.deepEqual(keyWindow('window-home', 0, 20 * M, 0, 20 * M), [0, 20 * M]);
  assert.deepEqual(keyWindow('window-end', 0, 20 * M, 0, 20 * M), [0, 20 * M]);
});

test('REQ-027 AC04: pointer and keyboard share the boundary clamp', () => {
  const H = 3600000, M = 60000;
  assert.equal(clampBoundary(0, 72 * H, 24 * H, 48 * H, 'start', 50 * H), 48 * H - 30 * M, 'start clamps to end minus 30 minutes');
  assert.equal(clampBoundary(0, 72 * H, 24 * H, 48 * H, 'start', -5 * H), 0, 'start clamps to the domain start');
  assert.equal(clampBoundary(0, 72 * H, 24 * H, 48 * H, 'end', 80 * H), 72 * H, 'end clamps to the domain end');
  assert.equal(clampBoundary(0, 72 * H, 24 * H, 48 * H, 'end', 24 * H + 10 * M), 24 * H + 30 * M, 'end clamps to start plus 30 minutes');
  assert.equal(minWindowSpan(0, 20 * M), 20 * M, 'a shorter domain lowers the floor to the available window');
  assert.equal(minWindowSpan(0, 72 * H), 30 * M);
});

test('REQ-027 AC02: navSliderSemantics tracks the live window in every control', () => {
  const H = 3600000, M = 60000;
  const sem = navSliderSemantics(0, 72 * H, 24 * H, 48 * H);
  assert.deepEqual(sem.window, { min: 0, max: 72 * H, now: 36 * H });
  assert.deepEqual(sem.start, { min: 0, max: 48 * H - 30 * M, now: 24 * H });
  assert.deepEqual(sem.end, { min: 24 * H + 30 * M, max: 72 * H, now: 48 * H });
  const moved = navSliderSemantics(0, 72 * H, 0, 6 * H);
  assert.deepEqual(moved.window, { min: 0, max: 72 * H, now: 3 * H });
  assert.deepEqual(moved.start, { min: 0, max: 6 * H - 30 * M, now: 0 });
  assert.deepEqual(moved.end, { min: 30 * M, max: 72 * H, now: 6 * H });
});

/* ---- REQ-028: keyboard-operable batch row expansion ---- */

test('REQ-028 AC01: rowDomIds qualifies row and detail ids by attention group', () => {
  ['slow', 'running', 'failure', 'all'].forEach(key => {
    const ids = rowDomIds('run-42', key);
    assert.equal(ids.rowId, `triton-batch-${key}-run-42`);
    assert.equal(ids.detailId, `triton-detail-${key}-run-42`);
  });
});

test('REQ-028 AC01: the same batch in overlapping groups keeps distinct row targets', () => {
  const rows = [];
  for (let i = 0; i < 12; i += 1) {
    rows.push({ id: `ok-${i}`, pr: 900 + i, title: `ok ${i}`, status: 'success', duration_seconds: 600 + i, start_at: '2026-10-07T10:00:00Z' });
  }
  rows.push({ id: 'run-42', pr: 942, title: 'overlap', status: 'failure', duration_seconds: 5000, start_at: '2026-10-07T11:00:00Z' });
  const groups = attentionGroups(rows, 700, '');
  const keys = groups.filter(g => g.rows.some(b => b.id === 'run-42')).map(g => g.key);
  assert.deepEqual(keys, ['slow', 'failure'], 'the batch is listed in both the slow and failure groups');
  const ids = keys.map(key => rowDomIds('run-42', key));
  assert.equal(new Set(ids.map(x => x.rowId)).size, ids.length, 'row ids stay unique across groups');
  assert.equal(new Set(ids.map(x => x.detailId)).size, ids.length, 'detail ids stay unique across groups');
});

/* ---- REQ-029: keyboard access to the pinned scatter cards ---- */

test('REQ-029 AC01: circleMark emits a focusable named button for keyboard users', () => {
  const b = { pr: 2331, e2e_index: 2, e2e_total: 3, sha: '6660627371475594e5ab6cd405d4b3791746cbe0', status: 'failure' };
  const html = circleMark(b, 10, 20, 5, '#f00', 'e2e');
  assert.ok(html.includes('role="button"'), 'the mark is a button');
  assert.ok(html.includes('tabindex="0"'), 'the mark is tabbable');
  assert.ok(html.includes('aria-label="E2E 详情：PR #2331 第 2/3 次 E2E 6660627"'), 'the identity label names the batch');
  const npu = circleMark(b, 10, 20, 5, '#f00', 'npu');
  assert.ok(npu.includes('aria-label="NPU 排队详情：PR #2331 第 2/3 次 E2E 6660627"'), 'NPU marks say what they show');
  assert.ok(npu.includes('data-kind="npu"'));
});

test('REQ-029 AC01: markLabel falls back for incomplete batch identity', () => {
  assert.ok(markLabel(null, 'e2e').includes('PR #?'));
  assert.ok(markLabel({}, 'e2e').includes('未关联 PR'));
  assert.ok(markLabel({}, 'e2e').includes('attempt 1'));
  assert.ok(markLabel({ pr: 1 }, 'npu').includes('未知'));
});

/* ---- REQ-029 AC02: placement keeps the pinned card off its anchor mark ---- */

test('REQ-029 AC02: placeTipBox places the card beside the mark with a gap by default', () => {
  const p = placeTipBox(100, 100, 430, 219, 1200, 800, 16, 16);
  assert.deepEqual(p, { x: 114, y: 114 });
  assert.ok(p.x >= 100 + 8, 'the card starts right of the 16×16 mark box');
});

test('REQ-029 AC02: placeTipBox flips above when bottom clamping would cover the mark', () => {
  // 764×485 viewport with the CSS-capped card height: the e2e dead-zone geometry from browser probing.
  const p = placeTipBox(438, 262, 430, 219, 764, 485, 16, 16);
  assert.deepEqual(p, { x: 322, y: 21 });
  assert.ok(p.y + 219 < 262 - 8, 'the card bottom stays above the mark box');
});

test('REQ-029 AC02: placeTipBox flips left when the card cannot fit above either', () => {
  // 300px-tall viewport: neither below nor above fits, so the cascade moves left of the mark.
  const p = placeTipBox(500, 80, 430, 219, 764, 300, 16, 16);
  assert.deepEqual(p, { x: 48, y: 12 });
  assert.ok(p.x + 430 < 500 - 8, 'the card right edge stays left of the mark box');
});

test('REQ-029 AC02: the capped card never covers the mark anywhere in a short viewport (grid)', () => {
  const vw = 764, vh = 485, w = 430;
  const h = Math.ceil(vh / 2 - 24); // the .tooltip CSS max-height cap at this viewport height
  for (let ax = 16; ax <= vw - 16; ax += 4) {
    for (let ay = 16; ay <= vh - 16; ay += 4) {
      const p = placeTipBox(ax, ay, w, h, vw, vh, 16, 16);
      const inViewport = p.x >= 12 && p.x + w <= vw - 12 && p.y >= 12 && p.y + h <= vh - 12;
      assert.ok(inViewport, `(${ax},${ay}) keeps the card inside the viewport`);
      const covers = p.x < ax + 8 && p.x + w > ax - 8 && p.y < ay + 8 && p.y + h > ay - 8;
      assert.ok(!covers, `(${ax},${ay}) must not cover the mark box`);
    }
  }
});

test('REQ-029 AC02: placeTipBox degrades to a clamped position when no escape exists', () => {
  // 369px card in a 485px viewport: 2h + 40 > vh leaves a dead zone where every
  // in-viewport placement covers the mark — the reason .tooltip caps max-height.
  const p = placeTipBox(438, 262, 430, 369, 764, 485, 16, 16);
  assert.deepEqual(p, { x: 12, y: 12 });
  assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y), 'no NaN even in the dead zone');
});

/* ---- REQ-031: x-axis label count adapts to the real plot width ---- */

test('REQ-031 AC01: axisTicks thins the label count as the plot narrows, endpoints always kept', () => {
  const s = +new Date('2026-10-06T08:13:00+08:00'), e = s + 72 * 3600000;
  const wide = axisTicks(s, e, 669, 77); // 1024px 视口实测绘图区
  assert.equal(wide.length, 7, 'wide plots keep the full density (capped)');
  assert.equal(wide[0], s, 'first tick is the window start');
  assert.equal(wide[wide.length - 1], e, 'last tick is the window end');
  const narrow = axisTicks(s, e, 195, 77); // 390px 视口实测绘图区
  assert.deepEqual(narrow, [s, e], 'a 195px plot only fits the two endpoint labels');
});

test('REQ-031 AC01: middle ticks divide the window evenly', () => {
  const s = 0, e = 72 * 3600000;
  assert.deepEqual(axisTicks(s, e, 400, 77), [0, 24 * 3600000, 48 * 3600000, 72 * 3600000], 'floor(410/87)=4 evenly spaced ticks');
});

test('REQ-031 AC01: degenerate widths and inputs still yield the two endpoints', () => {
  assert.deepEqual(axisTicks(100, 200, 0, 77), [100, 200]);
  assert.deepEqual(axisTicks(100, 200, -50, 77), [100, 200]);
  assert.deepEqual(axisTicks(100, 200, NaN, 77), [100, 200]);
  assert.deepEqual(axisTicks(new Date(100), new Date(200), 195, 77), [100, 200], 'Date inputs normalize');
});

test('REQ-031 AC02: a wider gap or label fits fewer labels', () => {
  assert.equal(axisTicks(0, 3600000, 500, 60, 10).length, 7, 'floor(510/70)=7');
  assert.equal(axisTicks(0, 3600000, 500, 60, 40).length, 5, 'floor(540/100)=5');
  assert.equal(axisTicks(0, 3600000, 500, 90, 10).length, 5, 'floor(510/100)=5');
});

test('REQ-031 AC01/AC03: both charts render adaptive ticks with edge anchors; fixed seven-label loops are gone', () => {
  const view = fs.readFileSync(path.join(__dirname, '..', 'web', 'triton-view.js'), 'utf8');
  assert.equal((view.match(/core\.axisTicks\(/g) || []).length, 2, 'E2E 与 NPU 两图都接入 axisTicks');
  assert.doesNotMatch(view, /i \* range \/ 6/, '固定 7 刻度循环已移除');
  assert.match(view, /first \? 'start' : last \? 'end' : 'middle'/, '首末标签锚定绘图区两端，杜绝越界裁切');
});

test('freshnessSlots finds the latest grace-elapsed Beijing slot', () => {
  // 2026-10-09 21:35 Beijing == 13:35 UTC: the 20:00 slot's 90-minute grace has elapsed.
  const now = Date.UTC(2026, 9, 9, 13, 35);
  const result = freshnessSlots(now, Date.UTC(2026, 9, 9, 11, 0));
  assert.equal(result.slots.length, 6);
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
