const { test } = require('node:test');
const assert = require('node:assert/strict');

const A = require('../web/eligibility.js');

test('P-008: cancelled/aborted is never rewritten into a failure', () => {
  assert.equal(A.normalizeExecutionResult('cancelled'), 'cancelled');
  assert.equal(A.normalizeExecutionResult('CANCELED'), 'cancelled');
  assert.equal(A.normalizeExecutionResult('aborted'), 'cancelled');
  assert.equal(A.normalizeExecutionResult('not_built'), 'cancelled');
  assert.equal(A.normalizeExecutionResult('failure'), 'failure');
});

test('P-008: unknown platform tokens map to unknown, not a guess', () => {
  assert.equal(A.normalizeExecutionResult('UNSTABLE'), 'unknown');
  assert.equal(A.normalizeExecutionResult(null), 'unknown');
  assert.equal(A.normalizeExecutionResult('success'), 'success');
  assert.equal(A.normalizeExecutionResult('in_progress'), 'running');
});

test('P-008: terminal results are exactly success/failure/cancelled', () => {
  assert.ok(A.isTerminal('success'));
  assert.ok(A.isTerminal('failure'));
  assert.ok(A.isTerminal('cancelled'));
  assert.ok(!A.isTerminal('running'));
  assert.ok(!A.isTerminal('unknown'));
});

test('P-008: per-metric eligibility is independent of other metrics', () => {
  assert.deepEqual(A.eligibilityFor('e2e', true), { metric: 'e2e', state: 'included', reason: null, profile_version: null });
  assert.deepEqual(A.eligibilityFor('x86', false, 'no valid task'), { metric: 'x86', state: 'excluded', reason: 'no valid task', profile_version: null });
  assert.deepEqual(A.eligibilityFor('dt', null), { metric: 'dt', state: 'unknown', reason: null, profile_version: null });
  assert.throws(() => A.eligibilityFor('', true), /requires a metric name/);
});

test('P-008: axes keep the three dimensions side by side without derivation', () => {
  const axes = A.axes(
    A.execution('success', 'SUCCESS'),
    A.evidence('approximate', ['起点近似'], 'attempt_start'),
    { e2e: A.eligibilityFor('e2e', true) }
  );
  assert.equal(axes.execution.result, 'success');
  assert.equal(axes.execution.raw_result, 'SUCCESS');
  assert.equal(axes.evidence.state, 'approximate');
  assert.deepEqual(axes.evidence.issues, ['起点近似']);
  assert.equal(axes.eligibility.e2e.state, 'included');
  // success may still carry an evidence gap — axes do not collapse it.
  assert.notEqual(axes.evidence.state, 'verified');
});

test('P-008: invalid axis values are rejected loudly', () => {
  assert.throws(() => A.execution('bogus'), /invalid execution result/);
  assert.throws(() => A.evidence('bogus'), /invalid evidence state/);
});