/* Workbench view (P-001, P-002, P-013): catalog-driven DOM rendering.

   The workbench is the default entry. It renders one project card per enabled
   project (via Workbench.projectCards) plus the de-duplicated "需要关注" table
   (via Shell.concernRows). Projects without data show an explicit unavailable
   status, never a fake zero. The pure HTML builders are exported for tests;
   ``mount`` injects them into a container. Depends on root.Workbench and
   root.Shell (workbench.js and shell.js, loaded first). */
(function (root) {
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function cardsHTML(catalog, statuses) {
    const cards = root.Workbench.projectCards(catalog, statuses || {});
    return cards.map(function (card) {
      const concern = card.concern_count == null ? '—' : card.concern_count;
      return (
        '<article class="project-card" data-project="' + esc(card.project_id) + '">' +
        '<div class="project-card-head"><h3>' + esc(card.display_name) + '</h3>' +
        '<span class="count">' + card.repository_count + ' 仓</span></div>' +
        '<dl>' +
        '<dt>本轮任务</dt><dd>' + esc(card.task_status_label) + '</dd>' +
        '<dt>数据</dt><dd>' + esc(card.data_mode_label) + '</dd>' +
        '<dt>窗口</dt><dd>' + (card.window_hours != null ? card.window_hours + 'h · ' + esc(card.time_basis || '') : '—') + '</dd>' +
        '<dt>关注</dt><dd>' + concern + '</dd>' +
        '</dl>' +
        '<div class="project-card-actions"><a class="button" href="#projects/' + esc(card.project_id) + '/overview">进入项目</a></div>' +
        '</article>'
      );
    }).join('');
  }

  function concernTableHTML(rows) {
    const list = rows || [];
    if (!list.length) return '<div class="empty" role="status">当前没有需要关注的记录</div>';
    const head = '<tr><th scope="col">项目</th><th scope="col">仓库</th><th scope="col">批次</th><th scope="col">原因</th><th scope="col">来源</th></tr>';
    const body = list.map(function (row) {
      const link = row.source_url
        ? '<a href="' + esc(row.source_url) + '" target="_blank" rel="noreferrer">查看</a>'
        : '—';
      return (
        '<tr><td>' + esc(row.project_id) + '</td>' +
        '<td>' + esc(row.repository_id) + '</td>' +
        '<td>' + esc(row.batch_id) + '</td>' +
        '<td>' + esc(row.reasons.join('、')) + '</td>' +
        '<td>' + link + '</td></tr>'
      );
    }).join('');
    return '<table class="concern-table"><thead>' + head + '</thead><tbody>' + body + '</tbody></table>';
  }

  function projectSelectorHTML(catalog, activeProjectId) {
    const projects = root.Shell.enabledProjects(catalog);
    const options = ['<option value="">全部项目</option>'].concat(
      projects.map(function (p) {
        const selected = p.project_id === activeProjectId ? ' selected' : '';
        return '<option value="' + esc(p.project_id) + '"' + selected + '>' + esc(p.display_name) + '</option>';
      })
    );
    return '<label>项目选择 <select id="projectSelector" aria-label="项目选择">' + options.join('') + '</select></label>';
  }

  function mount(container, model) {
    const m = model || {};
    const catalog = m.catalog || { projects: [] };
    const cards = cardsHTML(catalog, m.statuses || {});
    const concernHTML = concernTableHTML(m.concern_rows || []);
    const selector = projectSelectorHTML(catalog, m.active_project_id || '');
    container.innerHTML =
      '<div class="workbench-bar">' + selector + '</div>' +
      '<div class="workbench-cards">' + (cards || '<div class="empty" role="status">没有启用的项目</div>') + '</div>' +
      '<section class="panel"><div class="panel-head"><h2>需要关注</h2>' +
      '<p>按稳定批次身份计数，同一批次多原因合并为一行。</p></div>' + concernHTML + '</section>';
  }

  const api = { esc, cardsHTML, concernTableHTML, projectSelectorHTML, mount };
  if (typeof module !== 'undefined') module.exports = api;
  else root.WorkbenchView = api;
})(typeof window !== 'undefined' ? window : globalThis);