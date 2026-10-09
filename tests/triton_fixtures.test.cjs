const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { dashboardStats, startSourceLabel, markLabel, validDuration } = require('../web/triton-core.js');

const load = name => JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/minimal', name), 'utf8'));
const close = (actual, expected, msg) => assert.ok(Math.abs(actual - expected) < 1e-9, `${msg}: ${actual} != ${expected}`);

test('REQ-037 AC01: minimal fixture p90 is the interpolated 840, not the 900 sample', () => {
  const payload = load('triton.json');
  assert.equal(payload.summary.p90, 840);
  assert.notEqual(payload.summary.p90, 900);
  const stats = dashboardStats(payload.batches);
  close(stats.p90, 840, 'frontend p90');
  close(stats.median, 600, 'frontend median');
});

test('REQ-037 AC02: frontend dashboardStats recomputes the same summary from minimal batches', () => {
  const payload = load('triton.json');
  const stats = dashboardStats(payload.batches);
  assert.equal(stats.prs, 2);
  assert.equal(stats.batches, 5);
  assert.equal(stats.valid, 3);
  assert.equal(stats.incomplete, 1);
  assert.equal(stats.approximate, 5);
});

test('REQ-037 AC02: kind semantics — rerun start source and per-PR E2E labels', () => {
  const payload = load('triton.json');
  const rerun = payload.batches.find(b => b.kind === 'rerun');
  assert.ok(rerun, 'fixture carries a rerun batch');
  assert.equal(rerun.start_source, 'attempt_start');
  assert.equal(startSourceLabel(rerun), '本次重跑开始，近似');
  const initial = payload.batches.find(b => b.kind === 'initial');
  assert.equal(startSourceLabel(initial), '最早 workflow 创建，近似');
  assert.ok(markLabel(rerun, 'e2e').includes('第 2/3 次 E2E'));
});

test('REQ-037 AC03: zero-data fixture loads and stays legal zero', () => {
  const payload = load('triton-zero.json');
  const stats = dashboardStats(payload.batches);
  assert.equal(stats.batches, 0);
  assert.equal(stats.valid, 0);
  assert.equal(stats.median, null);
  assert.equal(stats.p90, null);
});

test('REQ-037 AC03: single-sample fixture expresses itself', () => {
  const payload = load('triton-single.json');
  const stats = dashboardStats(payload.batches);
  assert.equal(stats.valid, 1);
  close(stats.median, 720, 'median');
  close(stats.p90, 720, 'p90');
  assert.ok(validDuration(payload.batches[0].duration_seconds));
});

test('REQ-037 AC03: missing-value and running batches never join valid samples', () => {
  const payload = load('triton.json');
  const gap = payload.batches.find(b => b.duration_seconds === null);
  assert.deepEqual(gap.missing, ['无完成时间证据，E2E 留空']);
  assert.equal(validDuration(gap.duration_seconds), false);
  const running = payload.batches.find(b => b.status === 'running');
  assert.equal(running.end_at, null);
  assert.equal(dashboardStats(payload.batches).valid, 3);
});
