/* UDR-018 · unified batch records task — one common model for both projects.

   - default entity is batch; a PR entity is only offered where the project
     actually defines a PR E2E profile (UBS yes, Triton no), so a project
     without a PR E2E profile never fabricates a PR E2E aggregate.
   - sortRecords sorts the FULL set first (stable, unknown last, a legitimate
     0 participates, ties break by stable batch identity), and paginate only
     slices afterwards, so pagination can never reorder or drop rows.
   - normalize collapses each project's native batch rows into one record
     shape so the same records task renders both. */
(function (root) {
  'use strict';

  const PAGE_SIZES = [15, 30, 50];

  const SORT_KEYS = {
    duration: 'duration_ms', // E2E/duration
    queue: 'queue_ms',       // queue time
    start: 'start_at',       // batch start time
  };

  function identity(record) {
    if (record == null) return '';
    if (record.batch_id != null) return String(record.batch_id);
    if (record.url != null) return String(record.url);
    if (record.id != null) return String(record.id);
    return '';
  }

  /* A finite number participates in sorting (including a legitimate 0);
     null/undefined/non-finite is "unknown" and sorts last. */
  function numericValue(value) {
    if (typeof value === 'number') return Number.isFinite(value) ? value : null;
    if (value == null || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function sortRecords(records, key, dir) {
    const field = SORT_KEYS[key] || key;
    const sign = dir === 'asc' ? 1 : -1;
    const arr = (Array.isArray(records) ? records : []).slice();
    arr.sort(function (a, b) {
      const av = numericValue(a[field]);
      const bv = numericValue(b[field]);
      const aUnknown = av == null;
      const bUnknown = bv == null;
      if (aUnknown !== bUnknown) return aUnknown ? 1 : -1; // unknown last, any dir
      if (!aUnknown && av !== bv) return (av > bv ? 1 : -1) * sign;
      return identity(a).localeCompare(identity(b));       // stable identity tie-break
    });
    return arr;
  }

  function paginate(records, page, pageSize) {
    const size = PAGE_SIZES.indexOf(pageSize) !== -1 ? pageSize : 15;
    const total = (Array.isArray(records) ? records : []).length;
    const pages = Math.max(1, Math.ceil(total / size));
    const p = Math.min(Math.max(1, page == null ? 1 : page), pages);
    return {
      rows: records.slice((p - 1) * size, p * size),
      page: p,
      pages: pages,
      total: total,
      pageSize: size,
    };
  }

  /* Merge every page of a paginated sort back into one sequence, exactly as
     the browser does when it walks every page/size; used by TC01 to prove the
     sort survives pagination. */
  function mergePages(records, key, dir, pageSize) {
    const sorted = sortRecords(records, key, dir);
    const out = [];
    let page = 1;
    for (;;) {
      const slice = paginate(sorted, page, pageSize);
      out.push.apply(out, slice.rows);
      if (slice.page >= slice.pages) break;
      page += 1;
    }
    return out;
  }

  /* UBS: one batch record per (PR, batch) pair. */
  function ubsBatchRecords(snapshot) {
    const repo = snapshot && snapshot.meta ? snapshot.meta.repository : '';
    const out = [];
    for (const pr of (snapshot && snapshot.prs) || []) {
      for (const b of (pr.batches) || []) {
        out.push({
          entity: 'batch',
          project_id: 'ubs',
          repository_id: repo,
          batch_id: b.url || (pr.number + ':' + b.number),
          pr: pr.number,
          title: pr.title || '',
          status: b.status || 'unknown',
          duration_ms: b.e2e_ms,
          queue_ms: b.queue_ms,
          start_at: b.request_ms,
          end_at: b.end_ms,
          source_url: b.url || '',
        });
      }
    }
    return out;
  }

  /* Triton: one record per native batch row. PR identity is preserved when
     present but never invented. */
  function tritonBatchRecords(rows, repoId) {
    const repo = repoId || 'triton-ascend';
    return (rows || []).map(function (b) {
      return {
        entity: 'batch',
        project_id: 'triton',
        repository_id: repo,
        batch_id: b.id != null ? String(b.id) : (b.action_url || b.url || ''),
        pr: b.pr != null ? b.pr : null,
        title: b.title || '',
        status: b.status || 'unknown',
        duration_ms: b.duration_seconds != null ? b.duration_seconds * 1000 : null,
        queue_ms: b.npu_queue_seconds != null ? b.npu_queue_seconds * 1000 : null,
        start_at: b.start_at != null ? Date.parse(b.start_at) : null,
        end_at: b.end_at != null ? Date.parse(b.end_at) : null,
        source_url: b.action_url || b.pr_url || b.url || '',
      };
    });
  }

  function entityLabel(entity) {
    return entity === 'pr' ? 'PR' : '批次';
  }

  /* The PR entity is only offered where a PR E2E profile exists. */
  function entitiesForProject(projectId) {
    return projectId === 'ubs' ? ['batch', 'pr'] : ['batch'];
  }

  const api = {
    PAGE_SIZES,
    SORT_KEYS,
    identity,
    numericValue,
    sortRecords,
    paginate,
    mergePages,
    ubsBatchRecords,
    tritonBatchRecords,
    entityLabel,
    entitiesForProject,
  };
  if (typeof module !== 'undefined') module.exports = api;
  else root.Records = api;
})(typeof window !== 'undefined' ? window : globalThis);
