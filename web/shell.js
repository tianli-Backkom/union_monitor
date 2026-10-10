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

  const api = {
    FIXED_TASKS,
    taskLabel,
    enabledProjects,
    projectById,
    repositoryChoices,
    defaultRepositoryId,
    tasksForProject,
    concernRows,
  };
  if (typeof module !== 'undefined') module.exports = api;
  else root.Shell = api;
})(typeof window !== 'undefined' ? window : globalThis);