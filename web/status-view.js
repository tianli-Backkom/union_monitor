/* Three-axis project status view model (P-013).

   Mirrors monitor/status_view.py for the browser shell: task result, data
   version/mode, and data time are kept independent. A failed round reusing old
   data stays failed + fallback with the OLD collected_at; the publish time is
   never shown as if it were the data's collection time. */
(function (root) {
  const TASK_STATUSES = ['success', 'partial', 'failed', 'timeout', 'cancelled'];
  const DATA_MODES = ['fresh', 'fallback', 'unavailable'];

  function normTask(status) {
    return TASK_STATUSES.indexOf(status) !== -1 ? status : 'failed';
  }

  function normMode(mode) {
    return DATA_MODES.indexOf(mode) !== -1 ? mode : 'unavailable';
  }

  function taskAxis(report) {
    const r = report || {};
    const window = r.window || {};
    return {
      task_status: normTask(r.task_status),
      run_id: r.run_id,
      code_sha: r.code_sha,
      cutoff_at: window.end_at,
      started_at: r.started_at,
      finished_at: r.finished_at,
      exit_code: r.exit_code,
      error: r.error,
    };
  }

  function dataAxis(entry, report) {
    const e = entry || {};
    const r = report || {};
    return {
      data_mode: normMode(e.data_mode),
      snapshot_version: e.snapshot_version,
      snapshot_sha256: e.snapshot_sha256,
      metric_profile: e.metric_profile,
      validation_status: r.validation_status,
      source_release_id: e.source_release_id,
    };
  }

  function timeAxis(entry, opts) {
    const e = entry || {};
    const o = opts || {};
    const delayed = o.schedule_time && o.published_at ? o.published_at > o.schedule_time : null;
    return {
      collected_at: e.collected_at,
      window: e.window,
      published_at: o.published_at,
      schedule_time: o.schedule_time,
      delayed: delayed,
    };
  }

  function projectStatus(report, entry, opts) {
    return {
      task_result: taskAxis(report),
      data_version: dataAxis(entry, report),
      data_time: timeAxis(entry, opts),
    };
  }

  const api = { taskAxis, dataAxis, timeAxis, projectStatus };
  if (typeof module !== 'undefined') module.exports = api;
  else root.StatusView = api;
})(typeof window !== 'undefined' ? window : globalThis);