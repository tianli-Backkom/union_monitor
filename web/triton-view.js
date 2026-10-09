/* Triton-Ascend 门禁效率视图（合并看板 T8）。
   契约：window.TritonView.render(payload, container)，payload 为 web/data/triton.json。
   单一共享时间导航器同时驱动 E2E 与 NPU 两张散点图；每图各自保留状态 chips
   与 selection-stats；渲染逻辑移植自原独立看板 template.html（语义不变），
   视觉遵循 web/style.css 的令牌与组件词汇表（色值一律 var(--*)）。
   REQ-001 页级集合 G：所选目标分支 × 共享时间窗（按 start_at 含起止边界）内
   的全部批次；顶部汇总、状态数量、数据边界、关注/全部列表与两图的输入均从 G
   派生。E2E/NPU 状态 chips 只作用于对应图及图内统计；列表搜索只过滤列表。 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./triton-core.js'), globalThis);
  else root.TritonView = factory(root, root);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core, root) {
  'use strict';

  const HOUR = 3600000;
  const statusLabels = { success: '成功', failure: '失败', running: '执行中', cancelled: '取消', unknown: '未知' };
  const statusFill = {
    success: 'var(--ok)', failure: 'var(--danger)', running: 'var(--info)',
    cancelled: 'var(--warn)', unknown: 'var(--neutral)',
  };
  const focusDefs = [['a3-py310', 'A3 · py3.10'], ['a3-py311', 'A3 · py3.11'], ['a5-py312', 'A5 · py3.12']];
  const csvFields = ['pr', 'title', 'sha', 'base_branch', 'kind', 'start_at', 'end_at', 'status',
    'duration_seconds', 'npu_queue_seconds', 'approximate', 'start_source', 'critical_workflow', 'missing', 'pr_url', 'action_url'];

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const fmtDate = stamp => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(stamp));
  const dur = value => {
    if (value == null) return '—';
    if (value >= 3600) return (value / 3600).toFixed(value >= 36000 ? 0 : 1) + 'h';
    return Math.round(value / 60) + 'm';
  };
  const spanText = ms => {
    const hours = ms / HOUR;
    return hours < 24 ? hours.toFixed(hours < 10 ? 1 : 0) + ' 小时' : (hours / 24).toFixed(1) + ' 天';
  };
  const fillFor = status => statusFill[status] || statusFill.unknown;

  let active = null;
  let mounted = null;

  function render(payload, container) {
    if (core.sameSessionMount(mounted, payload, container)) return;
    const prevState = active ? active.state() : null;
    if (active) { active.destroy(); active = null; }
    mounted = null;
    if (!container) return;
    const batches = payload && Array.isArray(payload.batches) ? payload.batches : null;
    const domainStart = payload ? +new Date(payload.window_start) : NaN;
    const domainEnd = payload ? +new Date(payload.window_end) : NaN;
    if (!batches || !batches.length || !Number.isFinite(domainStart) || !Number.isFinite(domainEnd) || domainEnd <= domainStart) {
      container.innerHTML = '<div class="empty">暂无 Triton 门禁数据</div>';
      return;
    }
    mount(payload, container, domainStart, domainEnd, prevState);
  }

  function skeleton() {
    const legend = `<div class="legend">
      <span><i style="background:var(--ok)"></i>成功</span>
      <span><i style="background:var(--danger)"></i>失败</span>
      <span><i style="background:var(--warn)"></i>取消</span>
      <span><i style="background:var(--info)"></i>执行中</span>
    </div>`;
    return `
<div class="notice" data-role="freshness" role="status" hidden></div>
<div class="notice" data-role="windowNotice" role="status" hidden></div>
<div class="kpi-grid">
  <article class="kpi"><div class="kpi-label">涉及 PR</div><div class="kpi-value" data-role="kPr">—</div><small data-role="kPrNote">—</small></article>
  <article class="kpi"><div class="kpi-label">门禁批次</div><div class="kpi-value" data-role="kBatch">—</div><small data-role="kGap">—</small></article>
  <article class="kpi"><div class="kpi-label">中位 E2E</div><div class="kpi-value" data-role="kMedian">—</div><small data-role="kValid">—</small></article>
  <article class="kpi"><div class="kpi-label">P90 E2E</div><div class="kpi-value" data-role="kP90">—</div><small>页级范围 P90 · 兼作“耗时偏长”阈值；不代表 SLA</small></article>
</div>
<section class="global-filter">
  <strong>全局筛选</strong>
  <details class="branch-filter" data-role="branchFilter">
    <summary data-role="branchSummary">合入分支：全部</summary>
    <div class="branch-menu" data-role="branchOptions"></div>
  </details>
  <button type="button" class="chip" data-role="clearBranches">清除</button>
  <span class="results" data-role="statusPills"></span>
  <span class="filter-note">筛选会同步更新全部指标、图表和列表</span>
</section>
<section class="section">
  <div class="panel-head">
    <div><h2>PR E2E 执行时长</h2><p>每个点代表一次提交或一次手动重跑触发的 E2E；时间范围由下方导航器统一控制。</p></div>
    <div class="controls" data-role="e2eFilters">
      <button type="button" class="chip active" data-filter="all">全部</button>
      <button type="button" class="chip" data-filter="slow" title="以页级范围（分支×时间窗）的 P90 为阈值">耗时偏长</button>
      <button type="button" class="chip" data-filter="failure">失败</button>
      <button type="button" class="chip" data-filter="running">执行中</button>
    </div>
  </div>
  <div class="chart-wrap"><svg class="chart" data-role="chart" role="img" aria-label="PR E2E 执行时长"></svg></div>
  <div style="padding:0 20px 2px"><div class="selection-stats" data-role="e2eStats" aria-live="polite"></div></div>
  ${legend}
</section>
<section class="section">
  <div class="navigator" style="border-top:0">
    <div class="navigator-head"><strong>拖动或键盘选择时间范围 · 两张趋势图联动</strong><span data-role="selectedRange"></span></div>
    <svg class="nav-svg" data-role="navigator" role="group" aria-label="选择趋势图时间范围"></svg>
    <div class="range-control">
      <span class="range-label">快速选择</span>
      <button type="button" class="chip" data-hours="6">6 小时</button>
      <button type="button" class="chip" data-hours="12">12 小时</button>
      <button type="button" class="chip" data-hours="24">24 小时</button>
      <button type="button" class="chip" data-hours="48">48 小时</button>
      <button type="button" class="chip active" data-hours="72">72 小时</button>
      <span class="range-count" data-role="rangeCount"></span>
    </div>
  </div>
</section>
<section class="section">
  <div class="panel-head">
    <div><h2>NPU Job 排队时长</h2><p>每个点代表一次包含 NPU Job 的 E2E，纵轴取其子 NPU Job 中最长排队时长。</p></div>
    <div class="controls" data-role="npuFilters">
      <button type="button" class="chip active" data-npu-filter="all">全部</button>
      <button type="button" class="chip" data-npu-filter="failure">失败</button>
      <button type="button" class="chip" data-npu-filter="running">执行中</button>
    </div>
  </div>
  <div class="chart-wrap"><svg class="chart" data-role="npuChart" role="img" aria-label="NPU Job 排队时长"></svg></div>
  <div class="meta" data-role="npuDataNotice" role="status" style="padding:2px 20px 0"></div>
  <div style="padding:0 20px 2px"><div class="selection-stats" data-role="npuStats" aria-live="polite"></div></div>
  ${legend}
</section>
<section class="section">
  <div class="panel-head">
    <div><h2>需要关注的 PR</h2><p data-role="priorityNote"></p></div>
    <div class="table-actions"><button type="button" class="button" data-role="exportBatches"><svg class="icon icon-sm" aria-hidden="true"><use href="#i-download"/></svg>导出批次 CSV</button></div>
  </div>
  <div class="tools">
    <input type="search" data-role="search" placeholder="搜索 PR 编号或标题" aria-label="搜索关注列表">
    <button type="button" class="chip" data-role="showAll">查看全部批次</button>
  </div>
  <div class="attention" data-role="attention"></div>
</section>
<div class="foot"><strong>口径：</strong>E2E 从提交事件到该批次最后一项自动检查结束，包含排队与依赖等待；并行任务不相加。无法恢复精确提交事件时使用最早 workflow 创建时间，并在悬浮卡片中注明。成功和失败批次参与趋势；取消与运行中仅展示已观测耗时。<br><strong>数据边界：</strong><span data-role="boundary"></span></div>
<div class="tooltip" data-role="tip" tabindex="-1" role="dialog" aria-label="批次详情"></div>`;
  }

  function mount(D, container, domainStart, domainEnd, prevState) {
    container.innerHTML = skeleton();
    const el = selector => container.querySelector(selector);
    const all = selector => Array.from(container.querySelectorAll(selector));

    const chartSvg = el('[data-role="chart"]');
    const npuChartSvg = el('[data-role="npuChart"]');
    const navSvg = el('[data-role="navigator"]');
    const tip = el('[data-role="tip"]');
    const freshnessEl = el('[data-role="freshness"]');
    const branchOptionsEl = el('[data-role="branchOptions"]');
    const branchSummaryEl = el('[data-role="branchSummary"]');
    const statusPillsEl = el('[data-role="statusPills"]');
    const e2eStats = el('[data-role="e2eStats"]');
    const npuStats = el('[data-role="npuStats"]');
    const npuDataNotice = el('[data-role="npuDataNotice"]');
    const selectedRangeEl = el('[data-role="selectedRange"]');
    const rangeCountEl = el('[data-role="rangeCount"]');
    const priorityNoteEl = el('[data-role="priorityNote"]');
    const boundaryEl = el('[data-role="boundary"]');
    const attentionEl = el('[data-role="attention"]');
    const searchInput = el('[data-role="search"]');
    const showAllBtn = el('[data-role="showAll"]');
    const exportBtn = el('[data-role="exportBatches"]');
    const kPr = el('[data-role="kPr"]'), kBatch = el('[data-role="kBatch"]'), kGap = el('[data-role="kGap"]');
    const kMedian = el('[data-role="kMedian"]'), kP90 = el('[data-role="kP90"]'), kValid = el('[data-role="kValid"]');
    const kPrNote = el('[data-role="kPrNote"]');

    const selectedBranches = new Set(prevState ? prevState.branches : []);
    let filter = prevState && prevState.filter ? prevState.filter : 'all';
    let npuFilter = prevState && prevState.npuFilter ? prevState.npuFilter : 'all';
    let showAll = prevState ? !!prevState.showAll : false, tipPinned = false, tipTimer = 0, navDrag = null, lastPinnedMark = null;
    let viewStart, viewEnd;
    const recovered = prevState ? core.recoverWindow(prevState.start, prevState.end, domainStart, domainEnd) : null;
    if (recovered) {
      viewStart = recovered.start;
      viewEnd = recovered.end;
    } else {
      [viewStart, viewEnd] = core.windowForHours(domainStart, domainEnd, 72);
    }

    const branchPool = () => core.filterBranches(D.batches, selectedBranches);
    const pageSet = () => core.selectWindow(branchPool(), viewStart, viewEnd);
    const currentSummary = () => core.dashboardStats(pageSet());
    const searchPool = () => pageSet().filter(b => core.matchesQuery(b, searchInput.value));

    if (prevState) {
      if (prevState.search) searchInput.value = prevState.search;
      all('[data-filter]').forEach(x => x.classList.toggle('active', x.dataset.filter === filter));
      all('[data-npu-filter]').forEach(x => x.classList.toggle('active', x.dataset.npuFilter === npuFilter));
      if (recovered && recovered.adjusted) {
        const windowNoticeEl = el('[data-role="windowNotice"]');
        windowNoticeEl.hidden = false;
        windowNoticeEl.textContent = `快照更新：${recovered.reason}（当前选区 ${fmtDate(viewStart)} — ${fmtDate(viewEnd)}）`;
      }
    }

    function e2eRows(threshold) {
      return pageSet().filter(b => filter === 'all' || (filter === 'slow' && core.isSlow(b, threshold)) || b.status === filter);
    }

    function npuRows() {
      return pageSet().filter(b => core.validDuration(b.npu_queue_seconds) && (npuFilter === 'all' || b.status === npuFilter));
    }

    /* SVG presentation attributes do not accept var(), so status colors are
       applied as inline style fills after the marks are in the DOM. */
    function paintMarks(svg) {
      svg.querySelectorAll('.mark-hit .dot').forEach(dot => {
        const batch = D.batches[+dot.closest('.mark-hit').dataset.i];
        dot.style.fill = batch ? fillFor(batch.status) : statusFill.unknown;
      });
    }

    function draw() {
      const threshold = currentSummary().p90;
      const rows = e2eRows(threshold);
      const W = chartSvg.clientWidth || 900, H = 370, m = { l: 50, r: 22, t: 18, b: 42 };
      chartSvg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      const range = Math.max(viewEnd - viewStart, 1);
      const stats = core.chartStats(rows);
      const max = Math.max(stats.max * 1.12, 300);
      const x = t => m.l + (+new Date(t) - viewStart) / range * (W - m.l - m.r);
      const y = v => H - m.b - v / max * (H - m.t - m.b);
      let out = '';
      for (let i = 0; i <= 4; i++) {
        const yy = m.t + i * (H - m.t - m.b) / 4, val = max * (1 - i / 4);
        out += `<line class="gridline" x1="${m.l}" x2="${W - m.r}" y1="${yy}" y2="${yy}"/><text class="axis" x="${m.l - 8}" y="${yy + 3}" text-anchor="end">${dur(val)}</text>`;
      }
      for (let i = 0; i <= 6; i++) {
        const xx = m.l + i * (W - m.l - m.r) / 6;
        out += `<text class="axis" x="${xx}" y="${H - 13}" text-anchor="middle">${fmtDate(viewStart + i * range / 6)}</text>`;
      }
      if (stats.p90 != null) out += `<line class="p90-line" x1="${m.l}" x2="${W - m.r}" y1="${y(stats.p90)}" y2="${y(stats.p90)}"/>`;
      const bins = [];
      for (let a = viewStart; a < viewEnd; a += 6 * HOUR) {
        const vals = rows.filter(b => +new Date(b.start_at) >= a && +new Date(b.start_at) < a + 6 * HOUR && ['success', 'failure'].includes(b.status) && core.validDuration(b.duration_seconds))
          .map(b => b.duration_seconds).sort((p, q) => p - q);
        if (vals.length) {
          const mid = vals.length % 2 ? vals[(vals.length - 1) / 2] : (vals[vals.length / 2 - 1] + vals[vals.length / 2]) / 2;
          bins.push([x(Math.min(a + 3 * HOUR, viewEnd)), y(mid)]);
        }
      }
      if (bins.length > 1) out += `<path class="median-line" d="${bins.map((p, i) => (i ? 'L' : 'M') + p.join(',')).join(' ')}"/>`;
      /* REQ-017: batches without a valid observed duration are not plotted at a fake 0. */
      const ordered = rows.filter(b => core.validDuration(b.duration_seconds)).slice().sort((a, b) => (a.status === 'success' ? 0 : 1) - (b.status === 'success' ? 0 : 1));
      const raw = ordered.map(b => ({ x: x(b.start_at), y: y(b.duration_seconds || 0) }));
      const visual = core.spreadPoints(raw, 12, { minX: m.l, maxX: W - m.r, minY: m.t, maxY: H - m.b });
      ordered.forEach((b, i) => { out += core.circleMark(b, visual[i].x, visual[i].y, D.batches.indexOf(b), fillFor(b.status), 'e2e'); });
      chartSvg.innerHTML = out;
      paintMarks(chartSvg);
      const thresholdStat = `<div class="selection-stat metric"><span>耗时偏长阈值（页级 P90）</span><strong>${dur(threshold)}</strong></div>`;
      e2eStats.innerHTML = stats.count
        ? `<div class="selection-stat"><span>选区范围</span><strong>${spanText(viewEnd - viewStart)}</strong></div><div class="selection-stat"><span>有效样本</span><strong>${stats.count} 次</strong></div><div class="selection-stat metric"><span>平均（图内）</span><strong>${dur(stats.average)}</strong></div><div class="selection-stat metric"><span>P50（图内）</span><strong>${dur(stats.p50)}</strong></div><div class="selection-stat metric"><span>P90（图内）</span><strong>${dur(stats.p90)}</strong></div>${thresholdStat}`
        : `<div class="selection-empty">当前选区暂无已完成的有效样本</div>${thresholdStat}`;
      bindMarks();
    }

    function drawNpu() {
      const missing = pageSet()
        .filter(b => b.npu_data_missing && (npuFilter === 'all' || b.status === npuFilter)).length;
      npuDataNotice.textContent = missing
        ? `${missing} 个批次的 NPU 明细缺失或时间戳异常，未计入统计；缺失不代表没有排队。`
        : '排队时长按 GitHub Job 创建至开始时间计算。';
      const rows = npuRows();
      const W = npuChartSvg.clientWidth || 900, H = 370, m = { l: 50, r: 22, t: 18, b: 42 };
      npuChartSvg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      const range = Math.max(viewEnd - viewStart, 1);
      const stats = core.chartStats(rows.map(b => ({ ...b, duration_seconds: b.npu_queue_seconds })));
      const max = Math.max(stats.max * 1.12, 60);
      const x = t => m.l + (+new Date(t) - viewStart) / range * (W - m.l - m.r);
      const y = v => H - m.b - v / max * (H - m.t - m.b);
      let out = '';
      for (let i = 0; i <= 4; i++) {
        const yy = m.t + i * (H - m.t - m.b) / 4, val = max * (1 - i / 4);
        out += `<line class="gridline" x1="${m.l}" x2="${W - m.r}" y1="${yy}" y2="${yy}"/><text class="axis" x="${m.l - 8}" y="${yy + 3}" text-anchor="end">${dur(val)}</text>`;
      }
      for (let i = 0; i <= 6; i++) {
        const xx = m.l + i * (W - m.l - m.r) / 6;
        out += `<text class="axis" x="${xx}" y="${H - 13}" text-anchor="middle">${fmtDate(viewStart + i * range / 6)}</text>`;
      }
      if (stats.p90 != null) out += `<line class="p90-line" x1="${m.l}" x2="${W - m.r}" y1="${y(stats.p90)}" y2="${y(stats.p90)}"/>`;
      const bins = [];
      for (let a = viewStart; a < viewEnd; a += 6 * HOUR) {
        const vals = rows.filter(b => +new Date(b.start_at) >= a && +new Date(b.start_at) < a + 6 * HOUR)
          .map(b => b.npu_queue_seconds).sort((p, q) => p - q);
        if (vals.length) {
          const mid = vals.length % 2 ? vals[(vals.length - 1) / 2] : (vals[vals.length / 2 - 1] + vals[vals.length / 2]) / 2;
          bins.push([x(Math.min(a + 3 * HOUR, viewEnd)), y(mid)]);
        }
      }
      if (bins.length > 1) out += `<path class="median-line" d="${bins.map((p, i) => (i ? 'L' : 'M') + p.join(',')).join(' ')}"/>`;
      const ordered = rows.slice().sort((a, b) => (a.status === 'success' ? 0 : 1) - (b.status === 'success' ? 0 : 1));
      const raw = ordered.map(b => ({ x: x(b.start_at), y: y(b.npu_queue_seconds) }));
      const visual = core.spreadPoints(raw, 12, { minX: m.l, maxX: W - m.r, minY: m.t, maxY: H - m.b });
      ordered.forEach((b, i) => { out += core.circleMark(b, visual[i].x, visual[i].y, D.batches.indexOf(b), fillFor(b.status), 'npu'); });
      npuChartSvg.innerHTML = out;
      paintMarks(npuChartSvg);
      npuStats.innerHTML = stats.count
        ? `<div class="selection-stat"><span>选区范围</span><strong>${spanText(viewEnd - viewStart)}</strong></div><div class="selection-stat"><span>有效样本</span><strong>${stats.count} 次</strong></div><div class="selection-stat metric"><span>平均排队</span><strong>${dur(stats.average)}</strong></div><div class="selection-stat metric"><span>P50</span><strong>${dur(stats.p50)}</strong></div><div class="selection-stat metric"><span>P90</span><strong>${dur(stats.p90)}</strong></div>`
        : '<div class="selection-empty">当前选区暂无有效的 NPU 排队样本</div>';
      bindMarks();
    }

    function drawNavigator() {
      const rows = branchPool();
      const W = navSvg.clientWidth || 900, H = 72, p = { l: 4, r: 4, t: 6, b: 19 };
      const domain = domainEnd - domainStart;
      const x = t => p.l + (t - domainStart) / domain * (W - p.l - p.r);
      const plotH = H - p.t - p.b;
      navSvg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      /* REQ-027 AC03: remember which navigator control held focus before the
         innerHTML rebuild replaces it. */
      const activeMode = navSvg.contains(document.activeElement) && document.activeElement.dataset
        ? document.activeElement.dataset.drag : null;
      let out = `<rect class="nav-bg" x="${p.l}" y="${p.t}" width="${W - p.l - p.r}" height="${plotH}" rx="2"/>`;
      /* REQ-017: the navigator maps only valid durations onto its height axis. */
      const navRows = rows.filter(b => core.validDuration(b.duration_seconds));
      const max = Math.max(1, ...navRows.map(b => b.duration_seconds));
      navRows.forEach(b => {
        const cy = p.t + plotH - b.duration_seconds / max * (plotH - 5) - 2;
        out += `<circle class="nav-point" cx="${x(+new Date(b.start_at))}" cy="${cy}" r="1.6" style="fill:${fillFor(b.status)}"/>`;
      });
      const sx = x(viewStart), ex = x(viewEnd);
      out += `<rect class="nav-dim" x="${p.l}" y="${p.t}" width="${Math.max(0, sx - p.l)}" height="${plotH}"/>`;
      out += `<rect class="nav-dim" x="${ex}" y="${p.t}" width="${Math.max(0, W - p.r - ex)}" height="${plotH}"/>`;
      /* REQ-027 AC01/AC02: three named, focusable slider entries whose value
         semantics are rebuilt with every redraw. */
      const sem = core.navSliderSemantics(domainStart, domainEnd, viewStart, viewEnd);
      out += `<rect class="nav-selection" data-drag="window" role="slider" tabindex="0" aria-label="时间范围整体窗口" aria-valuemin="${sem.window.min}" aria-valuemax="${sem.window.max}" aria-valuenow="${sem.window.now}" aria-valuetext="${fmtDate(viewStart)} — ${fmtDate(viewEnd)}（${spanText(viewEnd - viewStart)}）" x="${sx}" y="${p.t}" width="${Math.max(1, ex - sx)}" height="${plotH}"/>`;
      for (const [side, xx] of [['start', sx], ['end', ex]]) {
        out += `<rect class="nav-handle" data-drag="${side}" role="slider" tabindex="0" aria-label="时间范围${side === 'start' ? '起点' : '终点'}" aria-valuemin="${sem[side].min}" aria-valuemax="${sem[side].max}" aria-valuenow="${sem[side].now}" aria-valuetext="${fmtDate(side === 'start' ? viewStart : viewEnd)}" x="${xx - 6}" y="${p.t - 2}" width="12" height="${plotH + 4}" rx="2"/>`;
        out += `<line class="nav-grip" x1="${xx - 2}" x2="${xx - 2}" y1="${p.t + 12}" y2="${p.t + plotH - 12}"/><line class="nav-grip" x1="${xx + 2}" x2="${xx + 2}" y1="${p.t + 12}" y2="${p.t + plotH - 12}"/>`;
      }
      out += `<text class="nav-axis" x="${p.l}" y="${H - 4}">${fmtDate(domainStart)}</text><text class="nav-axis" text-anchor="end" x="${W - p.r}" y="${H - 4}">${fmtDate(domainEnd)}</text>`;
      navSvg.innerHTML = out;
      /* REQ-027 AC03: redraws replace the inner DOM, so the focused control
         is restored on its rebuilt counterpart to keep focus visible. */
      if (activeMode) {
        const restored = navSvg.querySelector(`[data-drag="${activeMode}"]`);
        if (restored) restored.focus();
      }
      const hours = Math.round((viewEnd - viewStart) / HOUR);
      all('[data-hours]').forEach(b => b.classList.toggle('active', Math.abs(Number(b.dataset.hours) - hours) < 1 && Math.abs(viewEnd - domainEnd) < 60000));
      selectedRangeEl.textContent = `${fmtDate(viewStart)} — ${fmtDate(viewEnd)}`;
      rangeCountEl.textContent = spanText(viewEnd - viewStart);
    }

    const redrawAll = () => { draw(); drawNpu(); drawNavigator(); };

    function updateSummary() {
      const s = currentSummary(), pool = pageSet();
      kPr.textContent = s.prs;
      kBatch.textContent = s.batches;
      kGap.textContent = `${s.incomplete} 个批次存在证据缺口`;
      kMedian.textContent = dur(s.median);
      kP90.textContent = dur(s.p90);
      kValid.textContent = `基于 ${s.valid} 个已完成批次${s.valid > 0 && s.valid < 10 ? ' · 样本不足' : ''}`;
      kPrNote.textContent = `${spanText(viewEnd - viewStart)}内有提交批次`;
      boundaryEl.textContent = `${s.approximate} 个批次使用近似起点，${s.incomplete} 个批次存在明细或关联缺口。`;
      const counts = { success: 0, failure: 0, running: 0, cancelled: 0 };
      pool.forEach(b => { if (counts[b.status] != null) counts[b.status] += 1; });
      statusPillsEl.innerHTML = ['success', 'failure', 'running', 'cancelled']
        .map(key => `<span class="pill ${key}">${statusLabels[key]} ${counts[key]}</span>`).join('');
    }

    function renderBranchOptions() {
      const counts = {};
      D.batches.forEach(b => { counts[b.base_branch] = (counts[b.base_branch] || 0) + 1; });
      const rows = Object.entries(counts).sort((a, b) => a[0].localeCompare(b[0]));
      for (const branch of selectedBranches) if (!(branch in counts)) rows.push([branch, null]);
      branchOptionsEl.innerHTML = rows
        .map(([branch, count]) => `<label class="branch-option"><input type="checkbox" value="${esc(branch)}" ${selectedBranches.has(branch) ? 'checked' : ''}><b>${esc(branch)}</b><span>${count == null ? '本快照无批次' : count}</span></label>`).join('');
      branchSummaryEl.textContent = selectedBranches.size ? `合入分支：已选 ${selectedBranches.size} 项` : '合入分支：全部';
    }

    function updateGlobal() { updateSummary(); redrawAll(); renderRows(); }

    /* ---- tooltip card（pin 逻辑移植自原看板） ---- */
    function tipHtml(b) {
      const actions = (b.workflows || []).map(w => {
        const seconds = w.updated_at && w.created_at ? (new Date(w.updated_at) - new Date(w.created_at)) / 1000 : null;
        return `<div class="tip-action"><a href="${esc(w.url)}" target="_blank" rel="noopener">${esc(w.name)} ↗</a><span>${statusLabels[w.conclusion] || statusLabels[w.status] || esc(w.status)} · ${dur(seconds)}</span></div>`;
      }).join('');
      const jobs = focusDefs.map(([key, label]) => {
        const j = (b.focus_jobs || []).find(x => x.key === key);
        return j
          ? `<div class="tip-job"><a href="${esc(j.url)}" target="_blank" rel="noopener">${label} ↗</a><span>${j.status === 'completed' ? (j.conclusion === 'success' ? '完成' : '异常') : esc(j.status)}</span><span>排队 ${dur(j.wait_seconds)} · 执行 ${dur(j.run_seconds)}</span></div>`
          : `<div class="tip-job"><b>${label}</b><span class="missing">未触发或未发现该任务</span></div>`;
      }).join('');
      return `<div class="tip-head"><a href="${esc(b.action_url || (b.workflows && b.workflows[0] && b.workflows[0].url) || '#')}" target="_blank" rel="noopener">打开本次 GitHub Actions ↗</a><span>${statusLabels[b.status] || esc(b.status)} · ${dur(b.duration_seconds)}</span><button type="button" class="tip-close" aria-label="关闭详情"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button></div><div class="tip-title">PR #${b.pr || '?'} · 第 ${b.e2e_index || 1}/${b.e2e_total || 1} 次 E2E · ${esc((b.sha || '未知').slice(0, 7))}</div><div class="tip-summary"><a href="${esc(b.pr_url || '#')}" target="_blank" rel="noopener">查看 PR</a> · ${b.start_at ? fmtDate(b.start_at) + ' · ' + core.startSourceLabel(b) : core.startSourceLabel(b)}</div><div class="tip-actions"><div class="tip-label">本次 E2E 的 GitHub Actions</div>${actions}</div><div class="tip-jobs"><div class="tip-label">重点任务</div>${jobs}</div><div class="tip-hint">点击任一链接进入对应 GitHub Actions；点击散点可固定卡片。</div>`;
    }

    function npuTipHtml(b) {
      const jobs = (b.npu_jobs || []).slice().sort((a, c) => (c.wait_seconds || -1) - (a.wait_seconds || -1)).map(j =>
        `<div class="tip-job"><a href="${esc(j.url || b.action_url)}" target="_blank" rel="noopener">${esc(j.name)} ↗</a><span>${statusLabels[j.conclusion] || statusLabels[j.status] || esc(j.status)}</span><span>排队 ${dur(j.wait_seconds)}${j.measurement_error ? ' · ' + esc(j.measurement_error) : ''}</span></div>`).join('');
      return `<div class="tip-head"><a href="${esc(b.action_url || '#')}" target="_blank" rel="noopener">打开本次 GitHub Actions ↗</a><span>最长排队 ${dur(b.npu_queue_seconds)}</span><button type="button" class="tip-close" aria-label="关闭详情"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button></div><div class="tip-title">PR #${b.pr || '?'} · 第 ${b.e2e_index || 1}/${b.e2e_total || 1} 次 E2E · ${esc((b.sha || '未知').slice(0, 7))}</div><div class="tip-summary"><a href="${esc(b.pr_url || '#')}" target="_blank" rel="noopener">查看 PR</a> · ${fmtDate(b.start_at)}</div><div class="tip-jobs"><div class="tip-label">本次 E2E 的 NPU Jobs</div>${jobs}</div><div class="tip-hint">圆点取上述子任务中的最长排队时长。</div>`;
    }

    function placeTip(e, b, renderer) {
      showTip(e.clientX, e.clientY, b, renderer);
    }

    /* REQ-029: pointer and keyboard pinning share one show path; the
       keyboard path anchors the card to the mark's on-screen position.
       core.placeTipBox clamps into the viewport and flips above, then
       left of the 16×16 mark box so the card never covers the mark it
       was opened from; the .tooltip CSS max-height cap keeps an escape
       band open even in short viewports. */
    function showTip(x, y, b, renderer) {
      tip.innerHTML = renderer(b);
      tip.style.display = 'block';
      const p = core.placeTipBox(x, y, tip.offsetWidth, tip.offsetHeight, window.innerWidth, window.innerHeight, 16, 16);
      tip.style.left = p.x + 'px';
      tip.style.top = p.y + 'px';
    }

    /* REQ-029 AC02/AC03: one close path for Esc, the ✕ button and outside
       clicks — when focus was inside the card it returns to the originating
       mark, so hiding the card never leaves focus on a dead element. */
    function hideTip(fallback) {
      const wasInside = tip.contains(document.activeElement);
      tipPinned = false;
      tip.style.display = 'none';
      const target = fallback || lastPinnedMark;
      if (wasInside && target && target.isConnected) target.focus();
    }

    function bindMarks() {
      all('.mark-hit').forEach(mark => {
        const b = D.batches[+mark.dataset.i];
        if (!b) return;
        const html = mark.dataset.kind === 'npu' ? npuTipHtml : tipHtml;
        mark.onmouseenter = e => { clearTimeout(tipTimer); placeTip(e, b, html); };
        mark.onmousemove = e => { if (!tipPinned) placeTip(e, b, html); };
        mark.onmouseleave = () => { if (!tipPinned) tipTimer = setTimeout(() => hideTip(mark), 180); };
        mark.onclick = e => { e.stopPropagation(); tipPinned = true; lastPinnedMark = mark; placeTip(e, b, html); };
        /* REQ-029 AC01: SVG marks carry no native button activation, so
           Enter/Space pin the same card from the keyboard. */
        mark.onkeydown = e => {
          if (e.key !== 'Enter' && e.key !== ' ') return;
          e.preventDefault();
          tipPinned = true;
          lastPinnedMark = mark;
          const r = mark.getBoundingClientRect();
          showTip(r.x + r.width / 2, r.y + r.height / 2, b, html);
          tip.focus();
        };
      });
    }

    tip.onmouseenter = () => clearTimeout(tipTimer);
    tip.onmouseleave = () => { if (!tipPinned) hideTip(); };
    /* REQ-029 AC02: Esc and the ✕ button close the pinned card; focus that
       was inside returns to the originating mark. */
    tip.onkeydown = e => { if (e.key === 'Escape') { e.preventDefault(); hideTip(); } };
    tip.onclick = e => { if (e.target.closest('.tip-close')) { e.stopPropagation(); hideTip(); } };
    const onDocClick = e => {
      if (!e.target.closest('.tooltip') && !e.target.closest('.mark-hit')) hideTip();
    };
    document.addEventListener('click', onDocClick);

    /* ---- 关注列表（分组、搜索、展开、样本退化） ---- */
    function wfHtml(w, b) {
      const start = +new Date(b.start_at), end = +new Date(b.end_at || D.window_end);
      const total = Math.max(end - start, 1);
      const ws = +new Date(w.created_at), we = +new Date(w.updated_at || D.window_end);
      const left = Math.max(0, (ws - start) / total * 100);
      const width = Math.max(.5, (we - ws) / total * 100);
      const jobs = (w.jobs || []).length ? w.jobs.map(j => `<span class="${j.conclusion === 'failure' ? 'failed' : ''}">${esc(j.name)} · 等待 ${dur(j.wait_seconds)} / 执行 ${dur(j.run_seconds)}${(j.failed_steps || []).length ? ' · 失败步骤：' + j.failed_steps.map(esc).join('、') : ''}</span>`).join('') : '<span>job 明细未获取</span>';
      return `<div class="workflow"><div class="wf-name"><a class="link" href="${esc(w.url)}" target="_blank" rel="noopener">${esc(w.name)}</a> · #${w.attempt}</div><div class="track"><i class="bar ${w.conclusion || w.status}" style="left:${left}%;width:${Math.min(100 - left, width)}%"></i></div><div class="wf-time">${dur((we - ws) / 1000)}</div></div><div class="jobs">${jobs}</div>`;
    }

    function rowHtml(b, groupKey) {
      /* REQ-028 AC01: the expansion entry is a named button that declares its
         expanded state and controlled region; the row surface keeps working
         as a mouse shortcut through the row-main click handler. */
      const ids = core.rowDomIds(esc(b.id), groupKey);
      return `<article class="row" id="${ids.rowId}"><div class="row-main"><button type="button" class="row-toggle" aria-expanded="false" aria-controls="${ids.detailId}" aria-label="PR #${esc(b.pr || '?')} 批次明细"><svg class="icon" aria-hidden="true"><use href="#i-chevron-right"/></svg></button><div><a class="pr link" href="${esc(b.pr_url || '#')}" target="_blank" rel="noopener">PR #${b.pr || '?'}</a><div class="sub">${esc((b.sha || '未知').slice(0, 7))}${b.kind === 'rerun' ? ' · 重跑' : ''}</div></div><div class="title">${esc(b.title)}<div class="sub">${esc(b.author || '未知作者')} · ${esc(b.branch || '未知来源')} → ${esc(b.base_branch)}</div></div><div class="status ${esc(b.status)}">${statusLabels[b.status] || esc(b.status)}</div><div class="sub">${b.start_at ? fmtDate(b.start_at) : '起点未知'}</div><div class="duration">${dur(b.duration_seconds)}${b.approximate ? '*' : ''}</div><div class="critical">${b.status === 'running' ? '仍在等待 / 执行：' : '最后结束：'}${esc(b.critical_workflow || '未知')}</div></div><div class="detail" id="${ids.detailId}"><div class="detail-meta">起点：${b.start_at ? fmtDate(b.start_at) + '（' + core.startSourceLabel(b) + '）' : '无本次起点证据，E2E 留空'} · 合入分支：${esc(b.base_branch)} · ${b.end_at ? '结束：' + fmtDate(b.end_at) : '截至采集时间仍未结束'}</div>${(b.missing || []).map(x => `<div class="notice">${esc(x)}</div>`).join('')}${(b.workflows || []).map(w => wfHtml(w, b)).join('')}</div></article>`;
    }

    function renderRows() {
      const summary = currentSummary();
      showAllBtn.textContent = showAll ? '返回关注列表' : '查看全部批次';
      /* REQ-028 AC03: the innerHTML swaps below destroy the focused row;
         remember it so focus can return to the same row's toggle when it
         survives, or move to the search box when the row is gone. */
      const activeRow = attentionEl.contains(document.activeElement) ? document.activeElement.closest('.row') : null;
      const activeRowId = activeRow ? activeRow.id : null;
      if (!summary.batches) {
        priorityNoteEl.textContent = '当前分支与时间范围内没有批次。';
        attentionEl.innerHTML = '<div class="empty">当前合入分支与时间范围内没有批次，请调整分支筛选或扩大时间范围。</div>';
        restoreListFocus(activeRowId);
        return;
      }
      const pool = searchPool();
      /* REQ-026 AC01: the grouping strategy, threshold and labels come from G
         (pageSet) and its valid-sample count; the search only filters the rows
         inside each group and never changes the strategy. */
      const groups = showAll
        ? [{ key: 'all', label: '全部批次', rows: pool.slice().sort((a, b) => +new Date(b.start_at) - +new Date(a.start_at)) }]
        : core.attentionGroups(pageSet(), summary.p90, searchInput.value);
      priorityNoteEl.textContent = core.attentionNote(summary.valid);
      attentionEl.innerHTML = groups.map(group => `<div class="group-title">${group.label}<span class="count">${group.rows.length}</span></div><div class="rows">${group.rows.length ? group.rows.map(b => rowHtml(b, group.key)).join('') : '<div class="empty">当前没有此类批次</div>'}</div>`).join('');
      all('.row').forEach(row => {
        const main = row.querySelector('.row-main');
        main.onclick = e => {
          if (e.target.closest('a')) return; /* REQ-028 AC02: activating a link navigates, it must not also toggle the row */
          setRowOpen(row, !row.classList.contains('open'));
        };
      });
      restoreListFocus(activeRowId);
    }

    /* REQ-028 AC01: aria-expanded always mirrors the visible open state. */
    function setRowOpen(row, open) {
      row.classList.toggle('open', open);
      const btn = row.querySelector('.row-toggle');
      if (btn) btn.setAttribute('aria-expanded', String(open));
    }

    /* REQ-028 AC03: focus returns to the same row's toggle when the row
       survives the re-render, otherwise to the still-visible search box. */
    function restoreListFocus(activeRowId) {
      if (!activeRowId) return;
      const row = document.getElementById(activeRowId);
      const btn = row ? row.querySelector('.row-toggle') : null;
      if (btn) btn.focus();
      else searchInput.focus();
    }

    /* ---- 新鲜度：北京时间 8/13/18/20 槽位 + 90 分钟宽限，每分钟检查 ---- */
    function updateFreshness() {
      const result = core.freshnessSlots(Date.now(), D.collected_at);
      freshnessEl.hidden = !result.stale;
      freshnessEl.textContent = result.stale ? '数据更新已延迟：当前展示最后一次成功采集结果，请检查 GitHub Actions。' : '';
    }

    /* ---- 导出批次 CSV：G × 列表搜索后的完整唯一批次集合（字段与 triton-batches.csv 同集 16 项） ---- */
    async function exportBatches() {
      if (!root.Metrics || typeof root.Metrics.saveCsv !== 'function') return;
      exportBtn.disabled = true;
      let notice = container.querySelector('[data-role="exportNotice"]');
      if (!notice) {
        notice = document.createElement('div');
        notice.className = 'export-notice';
        notice.setAttribute('role', 'status');
        notice.setAttribute('data-role', 'exportNotice');
        container.insertBefore(notice, container.firstChild);
      }
      notice.textContent = '正在保存 CSV…';
      try {
        const rows = [csvFields, ...searchPool().map(b => csvFields.map(key =>
          key === 'missing' ? (b.missing || []).join('; ') : key === 'approximate' ? (b.approximate ? 'True' : 'False') : b[key] ?? ''))];
        const file = await root.Metrics.saveCsv(rows, 'triton-batches.csv');
        notice.innerHTML = file.mode === 'saved'
          ? `已保存到本地：<a href="${esc(file.url)}" download="${esc(file.name)}">${esc(file.name)} ↓</a>`
          : '已下载：' + esc(file.name);
      } catch (err) {
        notice.textContent = '导出失败：' + (err && err.message ? err.message : err);
      } finally {
        exportBtn.disabled = false;
      }
    }

    /* ---- 交互绑定 ---- */
    el('[data-role="e2eFilters"]').onclick = e => {
      const btn = e.target.closest('[data-filter]');
      if (!btn) return;
      filter = btn.dataset.filter;
      all('[data-filter]').forEach(x => x.classList.toggle('active', x === btn));
      draw();
    };
    el('[data-role="npuFilters"]').onclick = e => {
      const btn = e.target.closest('[data-npu-filter]');
      if (!btn) return;
      npuFilter = btn.dataset.npuFilter;
      all('[data-npu-filter]').forEach(x => x.classList.toggle('active', x === btn));
      drawNpu();
    };
    el('.range-control').onclick = e => {
      const btn = e.target.closest('[data-hours]');
      if (!btn) return;
      [viewStart, viewEnd] = core.windowForHours(domainStart, domainEnd, Number(btn.dataset.hours));
      tipPinned = false;
      tip.style.display = 'none';
      updateGlobal();
    };

    const navTime = e => {
      const rect = navSvg.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      return domainStart + x / rect.width * (domainEnd - domainStart);
    };
    navSvg.onpointerdown = e => {
      e.preventDefault();
      const mode = (e.target.dataset && e.target.dataset.drag) || 'jump';
      const at = navTime(e);
      if (mode === 'jump') {
        [viewStart, viewEnd] = core.moveWindow(domainStart, domainEnd, viewStart, viewEnd, at - (viewStart + viewEnd) / 2);
        navDrag = { mode: 'window', origin: at, start: viewStart, end: viewEnd };
      } else {
        navDrag = { mode, origin: at, start: viewStart, end: viewEnd };
      }
      navSvg.setPointerCapture(e.pointerId);
      updateGlobal();
    };
    navSvg.onpointermove = e => {
      if (!navDrag) return;
      const at = navTime(e), delta = at - navDrag.origin;
      if (navDrag.mode === 'window') [viewStart, viewEnd] = core.moveWindow(domainStart, domainEnd, navDrag.start, navDrag.end, delta);
      else if (navDrag.mode === 'start') viewStart = core.clampBoundary(domainStart, domainEnd, viewStart, viewEnd, 'start', navDrag.start + delta);
      else viewEnd = core.clampBoundary(domainStart, domainEnd, viewStart, viewEnd, 'end', navDrag.end + delta);
      updateGlobal();
    };
    navSvg.onpointerup = navSvg.onpointercancel = () => { navDrag = null; };
    /* REQ-027 AC01/AC04: keyboard operation of the shared time range; arrow
       keys move the window or adjust the focused boundary, Home/End reach the
       allowed edges, under the same constraints as pointer dragging. */
    navSvg.onkeydown = e => {
      const mode = e.target && e.target.dataset ? e.target.dataset.drag : null;
      if (!['window', 'start', 'end'].includes(mode)) return;
      const directions = { ArrowLeft: 'left', ArrowDown: 'left', ArrowRight: 'right', ArrowUp: 'right', Home: 'home', End: 'end' };
      const direction = directions[e.key];
      if (!direction) return;
      e.preventDefault();
      [viewStart, viewEnd] = core.keyWindow(`${mode}-${direction}`, domainStart, domainEnd, viewStart, viewEnd);
      updateGlobal();
    };

    branchOptionsEl.onchange = e => {
      if (!e.target.matches('input[type=checkbox]')) return;
      if (e.target.checked) selectedBranches.add(e.target.value);
      else selectedBranches.delete(e.target.value);
      renderBranchOptions();
      updateGlobal();
    };
    el('[data-role="clearBranches"]').onclick = () => { selectedBranches.clear(); renderBranchOptions(); updateGlobal(); };
    searchInput.oninput = renderRows;
    showAllBtn.onclick = () => { showAll = !showAll; renderRows(); };
    exportBtn.onclick = exportBatches;
    const onResize = () => redrawAll();
    window.addEventListener('resize', onResize);

    /* ---- 初始化 ---- */
    updateFreshness();
    const freshTimer = setInterval(updateFreshness, 60000);
    renderBranchOptions();
    updateGlobal();

    active = {
      destroy() {
        clearInterval(freshTimer);
        clearTimeout(tipTimer);
        window.removeEventListener('resize', onResize);
        document.removeEventListener('click', onDocClick);
      },
      state() {
        return { branches: [...selectedBranches], search: searchInput.value, filter, npuFilter, showAll, start: viewStart, end: viewEnd };
      },
    };
    mounted = { payload: D, container };
  }

  return { render };
});
