/* Unified time and unit display (P-009).

   Lists, KPIs, charts and timelines share one duration unit: minutes with two
   decimals. Formatting only affects presentation — it never mutates the
   numeric input used for computation. Values in milliseconds. */
(function (root) {
  const MIN = 60000;

  /* Complete terminal or real zero vs. unknown vs. small non-zero. */
  function minutes(ms) {
    if (ms == null || !Number.isFinite(ms) || ms < 0) return '—';
    if (ms === 0) return '0.00 min';
    if (ms < MIN * 0.01) return '<0.01 min';
    return (ms / MIN).toFixed(2) + ' min';
  }

  /* Unknown with the reason attached, never drawn as a zero point. */
  function missing(reason) {
    return '— · ' + (reason || '缺值');
  }

  function withReason(ms, reason) {
    return ms == null || !Number.isFinite(ms) || ms < 0 ? missing(reason) : minutes(ms);
  }

  /* Observed (running/cancelled without a terminal duration) is not a
     terminal time; it carries the "截至" marker and never fakes completion. */
  function observed(ms, asOfText) {
    return '已观测 ' + minutes(ms) + (asOfText ? ' · 截至 ' + asOfText : '');
  }

  /* Approximate origin values keep their approximation marker. */
  function approximate(ms) {
    return minutes(ms) + ' · 起点近似';
  }

  /* Detail/accessible exact value in seconds or milliseconds. */
  function exact(ms) {
    if (ms == null || !Number.isFinite(ms)) return '—';
    if (ms < 1000) return ms.toFixed(0) + ' ms';
    return (ms / 1000).toFixed(3) + ' s';
  }

  /* Self-expressive quantile, still not an SLA claim, small samples flagged. */
  function p90(ms, n) {
    return 'P90 ' + minutes(ms) + ' · n=' + n + (n <= 1 ? ' · 样本不足' : '');
  }

  const api = { minutes, missing, withReason, observed, approximate, exact, p90 };
  if (typeof module !== 'undefined') module.exports = api;
  else root.Units = api;
})(typeof window !== 'undefined' ? window : globalThis);