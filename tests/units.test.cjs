const { test } = require('node:test');
const assert = require('node:assert/strict');

const U = require('../web/units.js');

test('P-009: minutes unifies to two-decimal minutes with an explicit min label', () => {
  assert.equal(U.minutes(0), '0.00 min');
  assert.equal(U.minutes(60000), '1.00 min');
  assert.equal(U.minutes(1414000), '23.57 min'); // 1414s -> 23.5666.. min
});

test('P-009: a non-zero value below 0.01 min keeps the small-value marker', () => {
  assert.equal(U.minutes(100), '<0.01 min');
  assert.equal(U.minutes(599), '<0.01 min');
  assert.equal(U.minutes(600), '0.01 min');
});

test('UDR-006: minutesValue shares the public zero/unknown/small/extreme rules', () => {
  assert.equal(U.minutesValue(0), '0.00');        // real zero, not unknown
  assert.equal(U.minutesValue(100), '<0.01');     // tiny non-zero marker
  assert.equal(U.minutesValue(600), '0.01');
  assert.equal(U.minutesValue(null), '—');
  assert.equal(U.minutesValue(undefined), '—');
  assert.equal(U.minutesValue(NaN), '—');
  assert.equal(U.minutesValue(-5), '—');          // negative never coerced to zero
  assert.equal(U.minutesValue(60000), '1.00');
  // 21.68-day extreme value is retained, never dropped as "偏长".
  assert.equal(U.minutesValue(21.68 * 86400000), '31,219.20');
});

test('P-009: unknown is "—" with a reason, never a zero point', () => {
  assert.equal(U.minutes(null), '—');
  assert.equal(U.minutes(undefined), '—');
  assert.equal(U.minutes(NaN), '—');
  assert.equal(U.minutes(-5), '—');
  assert.equal(U.missing('缺请求起点'), '— · 缺请求起点');
  assert.equal(U.withReason(null, '缺请求起点'), '— · 缺请求起点');
  assert.equal(U.withReason(840000, '起点近似'), '14.00 min');
});

test('P-009: observed values never impersonate a terminal duration', () => {
  assert.equal(U.observed(492000, '2026-10-09 23:30'), '已观测 8.20 min · 截至 2026-10-09 23:30');
  assert.equal(U.observed(null, '2026-10-09 23:30'), '已观测 — · 截至 2026-10-09 23:30');
});

test('P-009: approximate origins keep their marker', () => {
  assert.equal(U.approximate(840000), '14.00 min · 起点近似');
});

test('P-009: exact detail value offers seconds or milliseconds precision', () => {
  assert.equal(U.exact(500), '500 ms');
  assert.equal(U.exact(1234), '1.234 s');
  assert.equal(U.exact(null), '—');
});

test('P-009: the P90 label is self-expressive and flags a small sample', () => {
  assert.equal(U.p90(840000, 1), 'P90 14.00 min · n=1 · 样本不足');
  assert.equal(U.p90(840000, 3), 'P90 14.00 min · n=3');
});