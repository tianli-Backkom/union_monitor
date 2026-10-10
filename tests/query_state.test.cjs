const { test } = require('node:test');
const assert = require('node:assert/strict');
const Q = require('../web/query-state.js');

const fields = [r => r.number, r => r.title, r => r.author, r => r.sha];

test('matchesQuery ignores blank and whitespace-only input', () => {
  assert.equal(Q.matchesQuery({ title: 'x' }, '', fields), true);
  assert.equal(Q.matchesQuery({ title: 'x' }, '   ', fields), true);
  assert.equal(Q.matchesQuery({ title: 'x' }, null, fields), true);
});

test('matchesQuery is case-insensitive across fields', () => {
  const record = { number: 248, title: 'Fix Queue', author: 'Alice', sha: 'abc123' };
  assert.equal(Q.matchesQuery(record, 'ALICE', fields), true);
  assert.equal(Q.matchesQuery(record, 'fix queue', fields), true);
  assert.equal(Q.matchesQuery(record, '248', fields), true);
  assert.equal(Q.matchesQuery(record, 'abc123', fields), true);
  assert.equal(Q.matchesQuery(record, 'notfound', fields), false);
});

test('selectList is always a subset of the analysis set', () => {
  const records = [
    { number: 1, title: 'Alpha' },
    { number: 2, title: 'Beta' },
    { number: 3, title: 'Alphabet' },
  ];
  const S = Q.selectAnalysis(records, () => true);
  const L = Q.selectList(S, 'alpha', [r => r.title]);
  assert.equal(S.length, 3);
  assert.deepEqual(L.map(r => r.number), [1, 3]);
});

test('a blank search reproduces the full analysis set without recomputation', () => {
  const records = [{ n: 1 }, { n: 2 }];
  const S = Q.selectAnalysis(records, () => true);
  const L = Q.selectList(S, '', []);
  assert.deepEqual(L, S);
});

test('analysis predicate selects S independently of any search', () => {
  const records = [
    { n: 1, state: 'open' },
    { n: 2, state: 'merged' },
    { n: 3, state: 'open' },
  ];
  const S = Q.selectAnalysis(records, r => r.state === 'open');
  assert.deepEqual(S.map(r => r.n), [1, 3]);
  const L = Q.selectList(S, 'zzz', [r => String(r.n)]);
  assert.deepEqual(L, []);
  assert.deepEqual(S.map(r => r.n), [1, 3]); // S unchanged by search
});

test('dedupeConcerns merges reasons under one stable batch id', () => {
  const concerns = [
    { batch: 'run:1:attempt:1', reason: '失败' },
    { batch: 'run:1:attempt:1', reason: '偏长' },
    { batch: 'run:2:attempt:1', reason: '失败' },
  ];
  const indexed = Q.dedupeConcerns(concerns, c => c.batch, c => [c.reason]);
  assert.equal(indexed.length, 2);
  const first = indexed.find(e => e.batchId === 'run:1:attempt:1');
  assert.deepEqual(first.reasons, ['失败', '偏长']);
});

test('concernSummary counts unique batches, with overlapping reasons', () => {
  const concerns = [
    { batch: 'b1', reason: '失败' },
    { batch: 'b1', reason: '偏长' },
    { batch: 'b2', reason: '执行中' },
    { batch: 'b2', reason: '证据缺口' },
  ];
  const summary = Q.concernSummary(Q.dedupeConcerns(concerns, c => c.batch, c => [c.reason]));
  assert.equal(summary.unique, 2);
  assert.deepEqual(summary.reasonCounts, { '失败': 1, '偏长': 1, '执行中': 1, '证据缺口': 1 });
});

test('dedupeConcerns skips rows without a stable identity', () => {
  const indexed = Q.dedupeConcerns([{ batch: '', reason: 'x' }], c => c.batch, c => [c.reason]);
  assert.equal(indexed.length, 0);
});