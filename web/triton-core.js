/* REQ-017: a valid duration is a finite, non-negative raw number. Missing,
   null, empty strings, numeric strings, NaN, infinities and negatives are
   never coerced into an implicit 0. Top-level so both module blocks below
   share this one definition. */
const validDuration = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
// E2E identity and measurement qualification are independent of NPU evidence.
// Explicitly unresolved old records must also be excluded; old records without
// identity/qualification fields retain the established numerical rules.
const e2eIdentityKnown = row => !(row && Object.prototype.hasOwnProperty.call(row, 'pr') && row.pr == null)
  && !(row && row.e2e_sample_eligible === false);
const sampleEligible = (row, metric = 'e2e') => !!row
  && (row.status === 'success' || row.status === 'failure') && validDuration(row.duration_seconds)
  && (metric === 'npu' ? !row.npu_data_missing : e2eIdentityKnown(row));

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
  function chartStats(rows, metric = 'e2e') {
    const observed = rows.map(row => row.duration_seconds).filter(validDuration);
    const completed = rows.filter(row => sampleEligible(row, metric))
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
    const completed = rows.filter(row => sampleEligible(row));
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

  /* REQ-014: one start-source label shared by hover card, batch detail and CSV. */
  const START_SOURCE_LABELS = { trigger_event: '触发事件', attempt_start: '本次重跑开始', workflow_created: '最早 workflow 创建' };
  function startSourceLabel(batch) {
    if (!batch || !batch.start_source) return '无起点证据';
    const base = START_SOURCE_LABELS[batch.start_source] || batch.start_source;
    return batch.approximate ? base + '，近似' : base;
  }

  /* REQ-029: stable identity label for a chart mark so keyboard users can
     locate a batch before opening its pinned detail card. */
  function markLabel(batch, kind) {
    if (batch && batch.pr == null) {
      const workflow = (batch.workflows || [])[0] || {};
      return (kind === 'npu' ? 'NPU 排队详情：' : '观测详情：') + '未关联 PR · Run #' + (workflow.id || batch.id || '?')
        + ' · attempt ' + (workflow.attempt || 1) + ' · ' + String(batch.sha || '未知').slice(0, 7);
    }
    const pr = batch && batch.pr != null ? batch.pr : '?';
    const attempt = `第 ${(batch && batch.e2e_index) || 1}/${(batch && batch.e2e_total) || 1} 次 E2E`;
    const sha = String((batch && batch.sha) || '未知').slice(0, 7);
    return (kind === 'npu' ? 'NPU 排队详情：PR #' : 'E2E 详情：PR #') + pr + ' ' + attempt + ' ' + sha;
  }

  function circleMark(batch, cx, cy, index, color, kind) {
    const radius = batch.status === 'success' ? 3.2 : 4.2;
    return `<g class="mark-hit" data-i="${index}" data-kind="${kind || 'e2e'}" role="button" tabindex="0" aria-label="${markLabel(batch, kind)}" transform="translate(${cx} ${cy})"><circle class="hit-area" r="8"/><circle class="dot" r="${radius}" fill="${color}"/></g>`;
  }

  return { selectWindow, windowForHours, moveWindow, spreadPoints, chartStats, filterBranches, dashboardStats, circleMark, markLabel, validDuration, sampleEligible, e2eIdentityKnown, startSourceLabel };
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
    return e2eIdentityKnown(batch) && validDuration(batch && batch.duration_seconds) && p90 != null && batch.status !== 'running' && batch.duration_seconds >= p90;
  }

  /* REQ-026: the strategy (P90 slow group vs top-5 longest), the threshold
     and the group labels are decided from G — the rows passed in — and its
     valid completed-sample count before any search filtering; the query only
     narrows the rows shown inside each already-decided group. */
  function attentionGroups(rows, p90, query) {
    const list = Array.isArray(rows) ? rows : [];
    const completed = list.filter(row => sampleEligible(row));
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
    const searched = row => matchesQuery(row, query);
    return [
      { key: 'slow', label: valid < 10 ? '耗时最长' : '耗时偏长', rows: slow.filter(searched) },
      { key: 'running', label: '执行中', rows: running.filter(searched) },
      { key: 'failure', label: '失败', rows: failure.filter(searched) },
    ];
  }

  /* REQ-026: the note names the same G sample denominator that picks the
     strategy and states that the three groups may overlap. */
  function attentionNote(valid) {
    const n = Number.isFinite(valid) ? valid : 0;
    return n < 10
      ? '有效完成样本少于 10 个（页级范围 ' + n + ' 个），展示耗时最长批次；理由计数可重叠，列表按稳定批次去重、每批次一行多标签。'
      : '优先显示超过 P90（按页级范围 ' + n + ' 个有效完成样本计算）、执行中和失败的批次；理由计数可重叠，列表按稳定批次去重、每批次一行多标签。';
  }

  /* REQ-028: stable DOM ids for one batch row. The attention groups may
     list the same batch in more than one group (failure ∩ slow), so ids
     carry the group key to keep aria-controls and focus restoration
     unambiguous when a batch appears twice. */
  function rowDomIds(batchId, groupKey) {
    const suffix = String(groupKey) + '-' + String(batchId);
    return { rowId: 'triton-batch-' + suffix, detailId: 'triton-detail-' + suffix };
  }

  /* REQ-027: the time-window constraints shared by pointer, touch and
     keyboard adjustments: stay inside the collection window and keep at
     least a 30-minute selection — or the whole window when the domain
     itself is shorter. */
  function minWindowSpan(domainStart, domainEnd) {
    return Math.min(30 * 60000, Math.max(0, domainEnd - domainStart));
  }

  function clampBoundary(domainStart, domainEnd, viewStart, viewEnd, side, value) {
    const minSpan = minWindowSpan(domainStart, domainEnd);
    if (side === 'start') return Math.max(domainStart, Math.min(value, viewEnd - minSpan));
    return Math.min(domainEnd, Math.max(value, viewStart + minSpan));
  }

  /* REQ-027: maps a keyboard action ("<mode>-<direction>") to the next
     selection. The step is a fraction of the current span so small windows
     fine-tune while large ones traverse quickly; Home/End reach the allowed
     edges. Pan and boundary actions apply the same constraints as pointer
     dragging (verified equivalent against moveWindow/clampBoundary by the
     Node tests). */
  function keyWindow(action, domainStart, domainEnd, viewStart, viewEnd) {
    const span = viewEnd - viewStart;
    const minSpan = minWindowSpan(domainStart, domainEnd);
    const step = Math.max(minSpan, span / 10);
    const whole = Math.min(span, domainEnd - domainStart);
    const clampStart = value => clampBoundary(domainStart, domainEnd, viewStart, viewEnd, 'start', value);
    const clampEnd = value => clampBoundary(domainStart, domainEnd, viewStart, viewEnd, 'end', value);
    const pan = delta => {
      const target = Math.max(domainStart, Math.min(domainEnd - span, viewStart + delta));
      return [target, target + span];
    };
    switch (action) {
      case 'window-left': return pan(-step);
      case 'window-right': return pan(step);
      case 'window-home': return [domainStart, domainStart + whole];
      case 'window-end': return [domainEnd - whole, domainEnd];
      case 'start-left': return [clampStart(viewStart - step), viewEnd];
      case 'start-right': return [clampStart(viewStart + step), viewEnd];
      case 'start-home': return [domainStart, viewEnd];
      case 'start-end': return [clampStart(viewEnd - minSpan), viewEnd];
      case 'end-left': return [viewStart, clampEnd(viewEnd - step)];
      case 'end-right': return [viewStart, clampEnd(viewEnd + step)];
      case 'end-home': return [viewStart, clampEnd(viewStart + minSpan)];
      case 'end-end': return [viewStart, domainEnd];
      default: return [viewStart, viewEnd];
    }
  }

  /* REQ-027: slider value semantics for the three navigator controls. The
     whole-window slider reports the window center over the domain; each
     boundary slider reports its edge position within its own allowed range
     (the other edge minus the minimum span). */
  function navSliderSemantics(domainStart, domainEnd, viewStart, viewEnd) {
    const minSpan = minWindowSpan(domainStart, domainEnd);
    return {
      window: { min: domainStart, max: domainEnd, now: Math.round((viewStart + viewEnd) / 2) },
      start: { min: domainStart, max: viewEnd - minSpan, now: viewStart },
      end: { min: viewStart + minSpan, max: domainEnd, now: viewEnd },
    };
  }

  function freshnessSlots(now, collectedAt) {
    const t = +new Date(now);
    const collected = collectedAt == null ? null : +new Date(collectedAt);
    const bj = new Date(t + 8 * 3600000);
    const day = Date.UTC(bj.getUTCFullYear(), bj.getUTCMonth(), bj.getUTCDate());
    const slots = [-4, 8, 12, 16, 18, 20]
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

  /* REQ-029 AC02: pure placement for the pinned detail card. The cascade
     clamps into the viewport, then flips above, then left of the anchor
     box (a focusable 16×16 mark) whenever clamping alone would pull the
     card back over it; the .tooltip CSS cap calc(50vh - 24px) keeps a
     vertical escape band open in every viewport (2h + 40 <= vh), so the
     above-flip always terminates the cascade in production. */
  function placeTipBox(ax, ay, width, height, vw, vh, markW, markH) {
    const pad = 12, gap = 14;
    const bx = ax - markW / 2, by = ay - markH / 2;
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(v, hi));
    const covers = (px, py) => px < bx + markW && px + width > bx && py < by + markH && py + height > by;
    let px = clamp(ax + gap, pad, Math.max(pad, vw - width - pad));
    let py = clamp(ay + gap, pad, Math.max(pad, vh - height - pad));
    if (covers(px, py)) py = clamp(by - height - gap, pad, Math.max(pad, vh - height - pad));
    if (covers(px, py)) px = clamp(bx - width - gap, pad, Math.max(pad, vw - width - pad));
    return { x: px, y: py };
  }

  /* REQ-031 AC01/AC02: the x-axis label count adapts to the real plot width.
     The window endpoints are always ticks and the rest divide the span
     evenly, so thinning labels only removes labels — it never moves marks
     or changes any statistic. */
  function axisTicks(start, end, plotWidth, labelWidth, gap = 10, maxTicks = 7) {
    const from = +new Date(start), to = +new Date(end);
    const span = Math.max(to - from, 1);
    const width = Number.isFinite(plotWidth) ? plotWidth : 0;
    const fit = Math.floor((width + gap) / (labelWidth + gap));
    const count = Math.min(maxTicks, Math.max(2, fit));
    const ticks = [];
    for (let i = 0; i < count; i++) ticks.push(from + (i * span) / (count - 1));
    return ticks;
  }

  /* REQ-033 AC01: 顶栏分支徽标文本——空选择=全部目标分支；单选=分支名；多选=数量并在 title 列出所选分支。 */
  function branchBadgeText(branches) {
    if (!branches.length) return { text: '全部目标分支' };
    if (branches.length === 1) return { text: branches[0] };
    const sorted = [...branches].sort();
    return { text: `已选 ${branches.length} 个分支`, title: sorted.join('、') };
  }

  return { isSlow, attentionGroups, attentionNote, rowDomIds, minWindowSpan, clampBoundary, keyWindow, navSliderSemantics, freshnessSlots, matchesQuery, sameSessionMount, recoverWindow, placeTipBox, axisTicks, branchBadgeText };
});
