/* Unified detail view model (P-007).

   One information hierarchy across projects: PR -> collected batches -> tasks
   -> source evidence. The pure builders normalise the two evidence structures
   (UBS request-event batches, Triton workflow/attempt batches) without erasing
   their differences. Opening a detail from a batch row expands that selected
   batch; opening from a PR row expands its representative batch; when there is
   no representative the most-recently collected batch is chosen with an
   explicit reason — never a fabricated representative value. */
(function (root) {
  const LIFECYCLE = { open: '开启中', merged: '已合入', closed: '已关闭未合入' };

  function lifecycleLabel(state) {
    return LIFECYCLE[state] || '未采集';
  }

  function detailTitle(projectId, repositoryLabel, entityNumber) {
    return [projectId, repositoryLabel, 'PR #' + entityNumber].join(' / ');
  }

  function byLatestEnd(a, b) {
    const ea = a && a.end_ms != null ? a.end_ms : (a && a.request_ms != null ? a.request_ms : 0);
    const eb = b && b.end_ms != null ? b.end_ms : (b && b.request_ms != null ? b.request_ms : 0);
    return eb - ea;
  }

  function matches(batch, id) {
    return batch.url === id || batch.number === id || batch.id === id;
  }

  /* Choose the batch to expand by default, with the reason why. */
  function defaultExpandedBatch(batches, opts) {
    const list = (batches || []).slice();
    const o = opts || {};
    if (o.entryId != null) {
      const hit = list.find(batch => matches(batch, o.entryId));
      if (hit) return { batch: hit, reason: 'entry' };
    }
    let rep = null;
    if (o.representativeUrl != null) rep = list.find(batch => batch.url === o.representativeUrl);
    if (!rep && o.representativeNumber != null) {
      rep = list.find(batch => batch.number === o.representativeNumber);
    }
    if (rep) return { batch: rep, reason: 'representative' };
    if (!list.length) return { batch: null, reason: 'empty' };
    return { batch: list.slice().sort(byLatestEnd)[0], reason: 'no-representative' };
  }

  /* Normalise a batch's trigger + child tasks into one timeline row list. */
  function taskTimeline(batch) {
    const trigger = (batch && batch.trigger) || {};
    const children = (batch && batch.children) || [];
    const all = [Object.assign({}, trigger, { kind: 'trigger' })].concat(children);
    return all.map(function (job) {
      return {
        role: job.kind === 'trigger' ? 'trigger' : 'task',
        kind: job.kind,
        number: job.number,
        url: job.url,
        wait_ms: job.queue_ms != null ? job.queue_ms : null,
        duration_ms: job.duration_ms != null ? job.duration_ms : null,
        total_ms: job.total_ms != null ? job.total_ms : null,
        result: job.result,
      };
    });
  }

  /* Detail provenance line: data version · collected time · evidence boundary. */
  function evidenceLine(opts) {
    const o = opts || {};
    const parts = [];
    if (o.snapshot_version) parts.push('数据版本 ' + o.snapshot_version);
    if (o.collected_at) parts.push('采集时间 ' + o.collected_at);
    if (o.boundary) parts.push('证据覆盖边界 ' + o.boundary);
    return parts.join(' · ');
  }

  const api = { lifecycleLabel, detailTitle, defaultExpandedBatch, taskTimeline, evidenceLine };
  if (typeof module !== 'undefined') module.exports = api;
  else root.Detail = api;
})(typeof window !== 'undefined' ? window : globalThis);