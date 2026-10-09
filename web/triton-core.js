/* REQ-017: a valid duration is a finite, non-negative raw number. Missing,
   null, empty strings, numeric strings, NaN, infinities and negatives are
   never coerced into an implicit 0. Top-level so both module blocks below
   share this one definition. */
const validDuration = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;

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

  /* REQ-017: chart/summary statistics count only valid durations. */
  function chartStats(rows) {
    const observed = rows.map(row => row.duration_seconds).filter(validDuration);
    const completed = rows.filter(row => (row.status === 'success' || row.status === 'failure') && validDuration(row.duration_seconds))
      .map(row => row.duration_seconds);
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
    const completed = rows.filter(row => (row.status === 'success' || row.status === 'failure') && validDuration(row.duration_seconds));
    const values = completed.map(row => row.duration_seconds);
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

  return { selectWindow, windowForHours, moveWindow, spreadPoints, chartStats, filterBranches, dashboardStats, circleMark, validDuration };
});

/* ---- T8 additions (appended; the prefix above is the original module plus
   REQ-017's validity filter, whose shared predicate is defined once at the
   top of this file). Merges the pure helpers of the standalone Triton
   dashboard into the shared core so the merged view and Node tests share one
   implementation. ---- */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) Object.assign(module.exports, api);
  else Object.assign(root, api);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function isSlow(batch, p90) {
    return validDuration(batch && batch.duration_seconds) && p90 != null && batch.status !== 'running' && batch.duration_seconds >= p90;
  }

  function attentionGroups(rows, p90) {
    const list = Array.isArray(rows) ? rows : [];
    const completed = list.filter(row => row.status === 'success' || row.status === 'failure');
    const valid = completed.filter(row => validDuration(row.duration_seconds)).length;
    let slow = list.filter(row => isSlow(row, p90))
      .sort((a, b) => (b.duration_seconds || 0) - (a.duration_seconds || 0));
    if (valid < 10) {
      slow = completed.filter(row => validDuration(row.duration_seconds)).slice()
        .sort((a, b) => b.duration_seconds - a.duration_seconds)
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

  function matchesQuery(batch, query) {
    const q = String(query || '').trim().toLowerCase();
    if (!q) return true;
    return String(batch.pr || '').includes(q) || String(batch.title || '').toLowerCase().includes(q);
  }

  function sameSessionMount(mounted, payload, container) {
    if (!mounted || mounted.payload !== payload || mounted.container !== container) return false;
    return !!(container && container.isConnected && container.children && container.children.length);
  }

  /* REQ-006：新采集窗口下的选区恢复。m = min(30 分钟, 新窗长 W)：原选区与新窗交集
     达到 m 时取交集（完全覆盖则原样保留），否则恢复新窗末尾长度
     L = min(W, max(原选区长, m)) 的窗口；返回 null 表示新窗口本身非法。 */
  function recoverWindow(oldStart, oldEnd, newStart, newEnd) {
    const MIN_MS = 30 * 60 * 1000;
    if (![newStart, newEnd].every(Number.isFinite) || newEnd <= newStart) return null;
    const W = newEnd - newStart;
    const m = Math.min(MIN_MS, W);
    if (![oldStart, oldEnd].every(Number.isFinite) || oldEnd <= oldStart) {
      return { start: newStart, end: newEnd, adjusted: false, reason: null };
    }
    const span = oldEnd - oldStart;
    const is = Math.max(oldStart, newStart);
    const ie = Math.min(oldEnd, newEnd);
    if (ie - is >= m) {
      const unchanged = is === oldStart && ie === oldEnd;
      return { start: is, end: ie, adjusted: !unchanged, reason: unchanged ? null : '原选区已按新采集窗口裁剪为交集' };
    }
    const L = Math.min(W, Math.max(span, m));
    return { start: newEnd - L, end: newEnd, adjusted: true, reason: '原选区与新采集窗口无有效交集，已恢复为新窗口末尾选区' };
  }

  return { isSlow, attentionGroups, freshnessSlots, matchesQuery, sameSessionMount, recoverWindow };
});
