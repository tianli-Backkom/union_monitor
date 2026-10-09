(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else Object.assign(root, api);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function selectWindow(rows, start, end) {
    return rows.filter(row => {
      const stamp = +new Date(row.start_at);
      return stamp >= start && stamp <= end;
    });
  }

  function windowForHours(domainStart, domainEnd, hours) {
    return [Math.max(domainStart, domainEnd - hours * 3600000), domainEnd];
  }

  function moveWindow(domainStart, domainEnd, start, end, delta) {
    const span = end - start;
    let nextStart = start + delta;
    let nextEnd = end + delta;
    if (nextStart < domainStart) return [domainStart, domainStart + span];
    if (nextEnd > domainEnd) return [domainEnd - span, domainEnd];
    return [nextStart, nextEnd];
  }

  function spreadPoints(points, threshold, bounds) {
    const placed = [];
    return points.map(point => {
      let candidate = { x: point.x, y: point.y }, step = 0;
      while (placed.some(p => Math.hypot(p.x - candidate.x, p.y - candidate.y) < threshold) && step < 80) {
        step += 1;
        const radius = threshold * .55 * Math.sqrt(step);
        const angle = step * 2.399963229728653;
        candidate = { x: point.x + Math.cos(angle) * radius, y: point.y + Math.sin(angle) * radius };
        if (bounds) candidate = {
          x: Math.max(bounds.minX, Math.min(bounds.maxX, candidate.x)),
          y: Math.max(bounds.minY, Math.min(bounds.maxY, candidate.y)),
        };
      }
      placed.push(candidate);
      return candidate;
    });
  }

  function percentile(values, q) {
    const sorted = values.slice().sort((a, b) => a - b);
    if (!sorted.length) return null;
    const position = (sorted.length - 1) * q;
    const lower = Math.floor(position), upper = Math.ceil(position);
    return lower === upper ? sorted[lower] : sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
  }

  function chartStats(rows) {
    const observed = rows.map(row => Number(row.duration_seconds)).filter(Number.isFinite);
    const completed = rows.filter(row => row.status === 'success' || row.status === 'failure')
      .map(row => Number(row.duration_seconds)).filter(Number.isFinite);
    return {
      max: observed.length ? Math.max(...observed) : 300,
      p90: percentile(completed, 0.9),
      p50: percentile(completed, 0.5),
      average: completed.length ? completed.reduce((sum, value) => sum + value, 0) / completed.length : null,
      count: completed.length,
    };
  }

  function filterBranches(rows, selected) {
    return selected && selected.size ? rows.filter(row => selected.has(row.base_branch)) : rows.slice();
  }

  function dashboardStats(rows) {
    const completed = rows.filter(row => (row.status === 'success' || row.status === 'failure') && Number.isFinite(Number(row.duration_seconds)));
    const values = completed.map(row => Number(row.duration_seconds));
    return {
      prs: new Set(rows.map(row => row.pr).filter(Boolean)).size,
      batches: rows.length,
      valid: completed.length,
      median: percentile(values, .5),
      p90: percentile(values, .9),
      incomplete: rows.filter(row => row.missing && row.missing.length).length,
      approximate: rows.filter(row => row.approximate).length,
    };
  }

  function circleMark(batch, cx, cy, index, color, kind) {
    const radius = batch.status === 'success' ? 3.2 : 4.2;
    return `<g class="mark-hit" data-i="${index}" data-kind="${kind || 'e2e'}" transform="translate(${cx} ${cy})"><circle class="hit-area" r="8"/><circle class="dot" r="${radius}" fill="${color}"/></g>`;
  }

  return { selectWindow, windowForHours, moveWindow, spreadPoints, chartStats, filterBranches, dashboardStats, circleMark };
});

/* ---- T8 additions (appended; the 3846-byte prefix above stays byte-identical
   to the original module). Merges the pure helpers of the standalone Triton
   dashboard into the shared core so the merged view and Node tests share one
   implementation. ---- */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) Object.assign(module.exports, api);
  else Object.assign(root, api);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function isSlow(batch, p90) {
    return batch != null && batch.duration_seconds != null && p90 != null && batch.status !== 'running' && batch.duration_seconds >= p90;
  }

  function attentionGroups(rows, p90) {
    const list = Array.isArray(rows) ? rows : [];
    const completed = list.filter(row => row.status === 'success' || row.status === 'failure');
    const valid = completed.filter(row => Number.isFinite(Number(row.duration_seconds))).length;
    let slow = list.filter(row => isSlow(row, p90))
      .sort((a, b) => (b.duration_seconds || 0) - (a.duration_seconds || 0));
    if (valid < 10) {
      slow = completed.slice()
        .sort((a, b) => (b.duration_seconds || 0) - (a.duration_seconds || 0))
        .slice(0, 5);
    }
    const running = list.filter(row => row.status === 'running')
      .sort((a, b) => (b.duration_seconds || 0) - (a.duration_seconds || 0));
    const failure = list.filter(row => row.status === 'failure')
      .sort((a, b) => +new Date(a.start_at) - +new Date(b.start_at));
    return [
      { key: 'slow', label: valid < 10 ? '耗时最长' : '耗时偏长', rows: slow },
      { key: 'running', label: '执行中', rows: running },
      { key: 'failure', label: '失败', rows: failure },
    ];
  }

  function freshnessSlots(now, collectedAt) {
    const t = +new Date(now);
    const collected = collectedAt == null ? null : +new Date(collectedAt);
    const bj = new Date(t + 8 * 3600000);
    const day = Date.UTC(bj.getUTCFullYear(), bj.getUTCMonth(), bj.getUTCDate());
    const slots = [-4, 8, 13, 18, 20]
      .map(hours => day + (hours - 8) * 3600000)
      .filter(slot => slot + 90 * 60000 <= t);
    const latest = slots.length ? Math.max(...slots) : null;
    const stale = latest != null && collected != null && collected < latest;
    return { slots, latest, stale };
  }

  return { isSlow, attentionGroups, freshnessSlots };
});
