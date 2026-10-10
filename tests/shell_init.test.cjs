const { test } = require('node:test');
const assert = require('node:assert/strict');
const ShellInit = require('../web/shell-init.js');

test('P-013: statusesFromRelease splits project entries from the time context', () => {
  const release = {
    release_id: 'rel-1',
    published_at: '2026-10-10T08:00:00Z',
    schedule_time: '2026-10-10T07:30:00Z',
    projects: { ubs: { task_status: 'success', data_mode: 'fresh' } },
  };
  const statuses = ShellInit.statusesFromRelease(release);
  assert.deepEqual(Object.keys(statuses.projects), ['ubs']);
  assert.equal(statuses.published_at, '2026-10-10T08:00:00Z');
  assert.equal(statuses.schedule_time, '2026-10-10T07:30:00Z');
});

test('P-013: statusesFromRelease degrades to empty projects and null times', () => {
  const statuses = ShellInit.statusesFromRelease(null);
  assert.deepEqual(statuses.projects, {});
  assert.equal(statuses.published_at, null);
  assert.equal(statuses.schedule_time, null);
});