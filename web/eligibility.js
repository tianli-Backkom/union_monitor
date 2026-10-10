/* Three independent quality axes — frontend mirror of monitor/status.py
   (T-008, P-008). Execution result, evidence integrity and per-metric
   eligibility are modeled separately; no component derives one from another.
   A cancelled execution is never rewritten into a failure, a success may still
   carry an evidence gap, and one excluded metric never drops the others. */
(function (root) {
  const EXECUTION_RESULTS = ['success', 'failure', 'running', 'cancelled', 'unknown'];
  const EVIDENCE_STATES = ['verified', 'approximate', 'missing', 'invalid', 'ambiguous'];
  const ELIGIBILITY_STATES = ['included', 'excluded', 'unknown'];
  const TERMINAL = ['success', 'failure', 'cancelled'];

  const SUCCESS = ['success', 'succeeded', 'passed'];
  const FAILURE = ['failure', 'failed', 'error'];
  const RUNNING = ['running', 'in_progress', 'inprogress', 'queued', 'building'];
  const CANCELLED = ['cancelled', 'canceled', 'aborted', 'not_built'];

  function normalizeExecutionResult(raw) {
    if (raw == null) return 'unknown';
    const token = String(raw).trim().toLowerCase();
    if (SUCCESS.indexOf(token) !== -1) return 'success';
    if (FAILURE.indexOf(token) !== -1) return 'failure';
    if (RUNNING.indexOf(token) !== -1) return 'running';
    if (CANCELLED.indexOf(token) !== -1) return 'cancelled';
    return 'unknown';
  }

  function isTerminal(result) {
    return TERMINAL.indexOf(result) !== -1;
  }

  function execution(result, rawResult) {
    if (EXECUTION_RESULTS.indexOf(result) === -1) {
      throw new Error('invalid execution result ' + String(result));
    }
    return { result: result, raw_result: rawResult == null ? null : rawResult };
  }

  function evidence(state, issues, source) {
    if (EVIDENCE_STATES.indexOf(state) === -1) {
      throw new Error('invalid evidence state ' + String(state));
    }
    return { state: state, issues: issues || [], source: source == null ? null : source };
  }

  /* Per-metric eligibility without borrowing other metrics. */
  function eligibilityFor(metric, eligible, reason, profileVersion) {
    if (!metric) throw new Error('eligibility requires a metric name');
    const state = eligible == null ? 'unknown' : (eligible ? 'included' : 'excluded');
    return {
      metric: metric,
      state: state,
      reason: reason == null ? null : reason,
      profile_version: profileVersion == null ? null : profileVersion,
    };
  }

  function axes(executionObj, evidenceObj, eligibilityMap) {
    return {
      execution: executionObj,
      evidence: evidenceObj,
      eligibility: eligibilityMap || {},
    };
  }

  const api = {
    EXECUTION_RESULTS, EVIDENCE_STATES, ELIGIBILITY_STATES,
    normalizeExecutionResult, isTerminal, execution, evidence, eligibilityFor, axes,
  };
  if (typeof module !== 'undefined') module.exports = api;
  else root.Axes = api;
})(typeof window !== 'undefined' ? window : globalThis);