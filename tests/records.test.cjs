const { test } = require('node:test');
const assert = require('node:assert/strict');
const R = require('../web/records.js');

const makeBatch = (id, duration) => ({
  batch_id: id,
  duration_ms: duration,
  queue_ms: 100,
  start_at: 1000,
});

/* UDR-018-TC01 · 31 batches with same sort value, 0 and unknown. */
const tc01 = [];
for (let i = 0; i < 10; i++) tc01.push(makeBatch(`b5000-${String(i).padStart(2, '0')}`, 5000));
for (let i = 0; i < 5; i++) tc01.push(makeBatch(`b0-${i}`, 0));
tc01.push(makeBatch('b-null-1', null));
tc01.push(makeBatch('b-null-2', undefined));
tc01.push(makeBatch('b-missing', undefined));
const distinct = [1300, 1200, 1100, 1000, 900, 800, 700, 600, 500, 400, 300, 200, 100];
distinct.forEach((d, i) => tc01.push(makeBatch(`b-${d}`, d)));
assert.equal(tc01.length, 31, 'fixture must be 31 batches');

const ids = rows => rows.map(r => r.batch_id);
const unique = rows => new Set(ids(rows)).size;

test('TC01: 31-batch full stable sort — no loss, no duplicate', () => {
  for (const key of ['duration', 'queue', 'start']) {
    for (const dir of ['asc', 'desc']) {
      const sorted = R.sortRecords(tc01, key, dir);
      assert.equal(sorted.length, 31, `${key}/${dir} length`);
      assert.equal(unique(sorted), 31, `${key}/${dir} no duplicate`);
      assert.deepEqual(ids(sorted).sort(), ids(tc01).sort(), `${key}/${dir} no loss`);
    }
  }
});

test('TC01: unknown sorts last and a legitimate 0 participates', () => {
  const desc = R.sortRecords(tc01, 'duration', 'desc');
  const tail = ids(desc).slice(-3);
  assert.deepEqual(tail.sort(), ['b-missing', 'b-null-1', 'b-null-2'], 'unknown last (desc)');
  const zeroes = desc.slice(desc.length - 8, desc.length - 3).map(r => r.duration_ms);
  assert.equal(zeroes.length, 5, 'zero preserved, not dropped');
  assert.ok(zeroes.every(v => v === 0), 'all five are 0');
  assert.ok(desc.slice(0, 23).every(r => r.duration_ms > 0), 'positive durations before zero');

  const asc = R.sortRecords(tc01, 'duration', 'asc');
  assert.deepEqual(ids(asc).slice(0, 5).sort(), ['b0-0', 'b0-1', 'b0-2', 'b0-3', 'b0-4'], 'zero first on asc');
  assert.deepEqual(ids(asc).slice(-3).sort(), ['b-missing', 'b-null-1', 'b-null-2'], 'unknown last (asc)');
});

test('TC01: same value ties break by stable batch identity', () => {
  const equal = [
    makeBatch('z', 42), makeBatch('a', 42), makeBatch('m', 42), makeBatch('b', 42),
  ];
  const sorted = R.sortRecords(equal, 'duration', 'desc');
  assert.deepEqual(ids(sorted), ['a', 'b', 'm', 'z'], 'ascending stable identity tie-break');
  // Deterministic regardless of input order.
  const reversed = R.sortRecords(equal.slice().reverse(), 'duration', 'desc');
  assert.deepEqual(ids(reversed), ['a', 'b', 'm', 'z'], 'order-independent');
});

test('TC01: pagination sizes 15/30/50 partition the sorted set', () => {
  const sorted = R.sortRecords(tc01, 'duration', 'desc');
  const p15 = R.paginate(sorted, 1, 15);
  assert.equal(p15.pages, 3);
  assert.equal(p15.rows.length, 15);
  assert.equal(p15.total, 31);
  assert.deepEqual(R.paginate(sorted, 3, 15).rows.length, 1, '15 → 15/15/1');
  const p30 = R.paginate(sorted, 1, 30);
  assert.equal(p30.pages, 2);
  assert.deepEqual(R.paginate(sorted, 2, 30).rows.length, 1, '30 → 30/1');
  const p50 = R.paginate(sorted, 1, 50);
  assert.equal(p50.pages, 1);
  assert.equal(p50.rows.length, 31, '50 → 31');
});

test('AC01: walking every page re-concatenates the full sort', () => {
  const merged = R.mergePages(tc01, 'duration', 'desc', 15);
  assert.deepEqual(merged, R.sortRecords(tc01, 'duration', 'desc'), 'pagination never reorders/drops');
  for (const size of [15, 30, 50]) {
    assert.equal(R.mergePages(tc01, 'queue', 'asc', size).length, 31, `size ${size}`);
  }
});

test('paginate clamps page into [1, pages] and keeps count', () => {
  const sorted = R.sortRecords(tc01, 'duration', 'desc');
  assert.equal(R.paginate(sorted, 99, 15).page, 3);
  assert.equal(R.paginate(sorted, 0, 15).page, 1);
  assert.equal(R.paginate(sorted, 1, 15).pageSize, 15);
  assert.equal(R.paginate(sorted, 1, 40).pageSize, 15, 'unknown size falls back to 15');
});

test('normalize: UBS flattens PR×batches into one record per batch', () => {
  const snapshot = {
    meta: { repository: 'ubs-engine' },
    prs: [
      { number: 100, title: 'A', batches: [
        { url: 'https://ci/x/1', number: 1, e2e_ms: 800, queue_ms: 50, request_ms: 1, end_ms: 2, status: 'success' },
        { url: 'https://ci/x/2', number: 2, e2e_ms: 900, queue_ms: 60, request_ms: 3, end_ms: 4, status: 'failure' },
      ] },
      { number: 101, title: 'B', batches: [
        { url: 'https://ci/x/3', number: 3, e2e_ms: null, queue_ms: 70, request_ms: 5, end_ms: 6, status: 'unknown' },
      ] },
    ],
  };
  const rows = R.ubsBatchRecords(snapshot);
  assert.equal(rows.length, 3);
  assert.ok(rows.every(r => r.entity === 'batch' && r.project_id === 'ubs' && r.repository_id === 'ubs-engine'));
  assert.deepEqual(rows.map(r => r.pr), [100, 100, 101]);
  assert.deepEqual(rows.map(r => r.duration_ms), [800, 900, null]);
});

test('normalize: Triton keeps present PR identity and never invents it', () => {
  const rows = R.tritonBatchRecords([
    { id: 'run-1', pr: 2513, duration_seconds: 12.5, npu_queue_seconds: 3, start_at: '2026-01-01T00:00:00Z', end_at: '2026-01-01T00:00:12Z', status: 'success', action_url: 'https://gh/a' },
    { id: 'run-2', pr: null, duration_seconds: 8, npu_queue_seconds: 1, start_at: '2026-01-02T00:00:00Z', end_at: '2026-01-02T00:00:08Z', status: 'failure', action_url: 'https://gh/b' },
  ], 'triton-ascend');
  assert.equal(rows.length, 2);
  assert.equal(rows[0].pr, 2513);
  assert.equal(rows[1].pr, null, 'unknown identity retained, not dropped');
  assert.equal(rows[0].duration_ms, 12500);
  assert.equal(rows[1].duration_ms, 8000);
  assert.equal(rows[1].queue_ms, 1000);
});

test('entities: Triton has no PR E2E profile, so no PR aggregate is fabricated', () => {
  assert.deepEqual(R.entitiesForProject('ubs'), ['batch', 'pr']);
  assert.deepEqual(R.entitiesForProject('triton'), ['batch']);
  assert.equal(R.entityLabel('batch'), '批次');
  assert.equal(R.entityLabel('pr'), 'PR');
});
