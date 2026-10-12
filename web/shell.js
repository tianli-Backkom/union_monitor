/* Dashboard shell view model (P-001, P-002, P-005).

   The shell presents one catalog-driven project selector and one fixed task
   navigation (not a top-level menu duplicated per project). The fixed tasks
   are stable; their secondary content is declared per project via the catalog
   view profile. Repositories expose the full ``source:owner/repo`` identity;
   a single-repository project auto-selects its only repository.

   Concern rows are de-duplicated by stable batch identity (one row per batch,
   many reason labels) so the "需要关注" count never sums overlapping reasons.
   Depends on ``root.QueryState`` (query-state.js) loaded first. */
(function (root) {
  const FIXED_TASKS = [
    { id: 'workbench', label: '工作台' },
    { id: 'overview', label: '项目概览' },
    { id: 'trends', label: '趋势与任务' },
    { id: 'records', label: 'PR 与批次' },
    { id: 'quality', label: '数据质量' },
    { id: 'collection', label: '数据与采集' },
    { id: 'metrics', label: '指标说明' },
  ];

  function taskLabel(taskId) {
    const task = FIXED_TASKS.find(function (t) { return t.id === taskId; });
    return task ? task.label : null;
  }

  function enabledProjects(catalog) {
    return (catalog && Array.isArray(catalog.projects) ? catalog.projects : [])
      .filter(function (p) { return p.enabled; });
  }

  function projectById(catalog, projectId) {
    return (catalog && Array.isArray(catalog.projects) ? catalog.projects : [])
      .find(function (p) { return p.project_id === projectId; }) || null;
  }

  function repositoryChoices(catalog, projectId) {
    const project = projectById(catalog, projectId);
    if (!project) return [];
    const repos = Array.isArray(project.repositories) ? project.repositories : [];
    const single = repos.length === 1;
    const choices = [{ id: 'all', label: '全部仓库', repository_id: null, is_default: !single }];
    for (const repo of repos) {
      choices.push({
        id: 'repo:' + repo.repository_id,
        label: repo.repository_id,
        repository_id: repo.repository_id,
        is_default: single,
      });
    }
    return choices;
  }

  function defaultRepositoryId(catalog, projectId) {
    const def = repositoryChoices(catalog, projectId).find(function (c) { return c.is_default; });
    return def ? def.repository_id : null;
  }

  function tasksForProject(catalog, projectId) {
    return FIXED_TASKS.map(function (t) { return { id: t.id, label: t.label }; });
  }

  function concernRows(concerns) {
    const qs = root.QueryState;
    if (!qs || typeof qs.dedupeConcerns !== 'function') {
      throw new Error('shell requires QueryState for concern de-duplication');
    }
    const indexed = qs.dedupeConcerns(
      concerns || [],
      function (c) { return c.batch_id; },
      function (c) { return c && c.reason ? [String(c.reason)] : []; }
    );
    return indexed.map(function (entry) {
      const item = entry.item || {};
      return {
        project_id: item.project_id,
        repository_id: item.repository_id,
        batch_id: entry.batchId,
        reasons: entry.reasons,
        source_url: item.source_url,
      };
    });
  }

  /* UDR-009: build the cross-project attention concern set. UBS batches use a
     repository-qualified stable identity (same-number PRs/batches in different
     repositories stay separate rows); collection-level errors keep their own
     source identity and never merge into a PR. Triton batches use the stable
     batch id, flag unknown PRs as an independent source identity and treat a
     P90-comparable duration as 偏长 without removing the failure/running flag. */
  function tritonP90(rows) {
    const completed = (rows || [])
      .filter(function (b) {
        return b && (b.status === 'success' || b.status === 'failure')
          && typeof b.duration_seconds === 'number' && Number.isFinite(b.duration_seconds) && b.duration_seconds >= 0
          && b.e2e_sample_eligible !== false
          && !(Object.prototype.hasOwnProperty.call(b, 'pr') && b.pr == null);
      })
      .map(function (b) { return b.duration_seconds; })
      .sort(function (a, b) { return a - b; });
    if (!completed.length) return null;
    const pos = (completed.length - 1) * 0.9, lo = Math.floor(pos), hi = Math.ceil(pos);
    return lo === hi ? completed[lo] : completed[lo] + (completed[hi] - completed[lo]) * (pos - lo);
  }

  function buildWorkbenchConcerns(repositorySnapshots, tritonPayload) {
    const concerns = [];
    for (const entry of Object.values(repositorySnapshots || {})) {
      const repo = entry && entry.meta && entry.meta.repository;
      if (!repo) continue;
      for (const p of entry.prs || []) {
        for (const reason of p.issues || []) concerns.push({ project_id: 'ubs', repository_id: repo, batch_id: repo + '#PR' + p.number, reason: String(reason), source_url: p.url || '' });
        for (const b of p.batches || []) {
          const bid = repo + '#' + p.number + '::' + b.number;
          if (b.status === 'failure') concerns.push({ project_id: 'ubs', repository_id: repo, batch_id: bid, reason: '失败', source_url: b.url || '' });
          for (const reason of b.issues || []) concerns.push({ project_id: 'ubs', repository_id: repo, batch_id: bid, reason: String(reason), source_url: b.url || '' });
        }
      }
      for (const e of (entry.meta && Array.isArray(entry.meta.errors) ? entry.meta.errors : [])) concerns.push({ project_id: 'ubs', repository_id: repo, batch_id: repo + '::collection:' + (e.source || ''), reason: '采集 ' + (e.reason || ''), source_url: '' });
    }
    if (tritonPayload && Array.isArray(tritonPayload.batches)) {
      const repoId = 'github:triton-lang/triton-ascend';
      const p90 = tritonP90(tritonPayload.batches);
      for (const b of tritonPayload.batches) {
        const reasons = [];
        if (b.status === 'failure') reasons.push('失败');
        else if (b.status === 'running') reasons.push('执行中');
        if (b.pr == null) reasons.push('未知 PR 身份');
        if (p90 != null && b.status !== 'running' && b.duration_seconds >= p90) reasons.push('耗时偏长');
        const url = b.action_url || (b.workflows && b.workflows[0] && b.workflows[0].url) || '';
        for (const reason of reasons) concerns.push({ project_id: 'triton', repository_id: repoId, batch_id: repoId + '#' + String(b.id), reason: reason, source_url: url });
      }
    }
    return concerns;
  }

  const api = {
    FIXED_TASKS,
    taskLabel,
    enabledProjects,
    projectById,
    repositoryChoices,
    defaultRepositoryId,
    tasksForProject,
    concernRows,
    buildWorkbenchConcerns,
  };
  if (typeof module !== 'undefined') module.exports = api;
  else root.Shell = api;
})(typeof window !== 'undefined' ? window : globalThis);