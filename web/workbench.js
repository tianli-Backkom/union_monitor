/* Workbench view model (P-001, P-013).

   The workbench presents each enabled project as a card showing the current
   scope, data time, collection status, concern count and explainable metrics.
   A project whose data is unavailable shows its status rather than a fake zero
   concern count; concern counts come from a stable batch identity, never from
   summing overlapping reason labels. */
(function (root) {
  const TASK_LABELS = { success: '成功', partial: '部分', failed: '失败', timeout: '超时', cancelled: '取消' };
  const MODE_LABELS = { fresh: '新数据', fallback: '回退', unavailable: '不可用' };

  function taskLabel(status) {
    return TASK_LABELS[status] || status;
  }

  function modeLabel(mode) {
    return MODE_LABELS[mode] || mode;
  }

  function enabledProjects(catalog) {
    return (catalog && Array.isArray(catalog.projects) ? catalog.projects : []).filter(function (p) { return p.enabled; });
  }

  /* Count unique concerns by stable batch identity; missing/empty ids are not
     counted. Returns null for no concern list at all (unknown), not 0. */
  function countConcernsByBatch(concerns) {
    if (!Array.isArray(concerns)) return null;
    const ids = new Set();
    for (const concern of concerns) {
      const id = concern && concern.batch_id;
      if (id != null && id !== '') ids.add(id);
    }
    return ids.size;
  }

  function projectCard(project, status) {
    const s = status || {};
    const repos = Array.isArray(project.repositories) ? project.repositories : [];
    const available = s.data_mode === 'fresh' || s.data_mode === 'fallback';
    const concernCount = !available
      ? null
      : (typeof s.concern_count === 'number' ? s.concern_count : countConcernsByBatch(s.concerns));
    return {
      project_id: project.project_id,
      display_name: project.display_name || project.project_id,
      repository_count: repos.length,
      window_hours: project.window && project.window.hours != null ? project.window.hours : null,
      time_basis: project.window ? project.window.time_basis : null,
      task_status: s.task_status || 'failed',
      task_status_label: taskLabel(s.task_status || 'failed'),
      data_mode: s.data_mode || 'unavailable',
      data_mode_label: modeLabel(s.data_mode || 'unavailable'),
      available: available,
      collected_at: s.collected_at || null,
      concern_count: concernCount,
    };
  }

  function projectCards(catalog, statuses) {
    const byProject = statuses || {};
    return enabledProjects(catalog).map(function (project) {
      return projectCard(project, byProject[project.project_id]);
    });
  }

  const api = { taskLabel, modeLabel, enabledProjects, countConcernsByBatch, projectCard, projectCards };
  if (typeof module !== 'undefined') module.exports = api;
  else root.Workbench = api;
})(typeof window !== 'undefined' ? window : globalThis);