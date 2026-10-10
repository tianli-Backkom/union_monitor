const { test } = require('node:test');
const assert = require('node:assert/strict');
const StatusView = require('../web/status-view.js');

test('P-013: three axes stay independent for a failed round reusing old data', () => {
  const report = {
    task_status: 'failed',
    run_id: 'run-2',
    code_sha: '0'.repeat(40),
    started_at: '2026-10-10T07:30:00Z',
    finished_at: '2026-10-10T07:35:00Z',
    exit_code: 1,
    error: 'source down',
  };
  const entry = {
    data_mode: 'fallback',
    snapshot_version: 'old-v3',
    snapshot_sha256: 'bb'.repeat(32),
    collected_at: '2026-10-09T00:10:00Z',
    window: { time_basis: 'pr_created_at', start_at: '2026-09-09T00:00:00Z', end_at: '2026-10-09T23:30:00Z' },
  };
  const status = StatusView.projectStatus(report, entry, {
    published_at: '2026-10-10T08:00:00Z',
    schedule_time: '2026-10-10T07:30:00Z',
  });
  assert.equal(status.task_result.task_status, 'failed');
  assert.equal(status.data_version.data_mode, 'fallback');
  assert.equal(status.data_time.collected_at, '2026-10-09T00:10:00Z');
  assert.equal(status.data_time.window.end_at, '2026-10-09T23:30:00Z');
  assert.notEqual(status.data_time.collected_at, status.data_time.published_at);
});

test('P-013: normalization maps bogus task/mode to failed/unavailable', () => {
  assert.equal(StatusView.taskAxis({ task_status: 'bogus' }).task_status, 'failed');
  assert.equal(StatusView.dataAxis({ data_mode: 'weird' }).data_mode, 'unavailable');
  assert.equal(StatusView.dataAxis(null).data_mode, 'unavailable');
});

test('P-013: delayed is an observation, null without a schedule', () => {
  const t = StatusView.timeAxis({}, { published_at: '2026-10-10T08:00:00Z' });
  assert.equal(t.delayed, null);
  const late = StatusView.timeAxis({}, { published_at: '2026-10-10T08:00:00Z', schedule_time: '2026-10-10T07:30:00Z' });
  assert.equal(late.delayed, true);
});