/* Workbench bootstrap (P-001, P-013): read the published catalog + release and
   mount the catalog-driven workbench. The workbench renders with an explicit
   unavailable status when no release data exists yet; it never fakes zeroes. */
(function (root) {
  function fetchJSON(url) {
    return fetch(url).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status + ' ' + url);
      return response.json();
    });
  }

  /* Pure statuses mapping: the release manifest's per-project entries already
     carry task_status/data_mode/collected_at; the top-level published_at /
     schedule_time feed the time axis so a delayed publish is shown as an
     observation, never as a re-collection. */
  function statusesFromRelease(release) {
    return {
      projects: (release && release.projects) || {},
      published_at: release && release.published_at,
      schedule_time: release && release.schedule_time,
    };
  }

  async function init(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    try {
      const catalog = await fetchJSON('data/catalog.json');
      let release = null;
      try {
        release = await fetchJSON('data/release.json');
      } catch (err) {
        release = null; // no release yet: workbench shows explicit unavailable states
      }
      const statuses = statusesFromRelease(release);
      root.WorkbenchView.mount(container, {
        catalog: catalog,
        statuses: statuses.projects,
        time: { published_at: statuses.published_at, schedule_time: statuses.schedule_time },
        concern_rows: [],
      });
      container.setAttribute('data-state', 'ready');
    } catch (err) {
      container.innerHTML = '<div class="empty" role="status">工作台目录读取失败：请确认已发布目录，或运行 python scripts/devdata.py 后重载。</div>';
      container.setAttribute('data-state', 'error');
    }
  }

  const api = { fetchJSON, statusesFromRelease, init };
  if (typeof module !== 'undefined') module.exports = api;
  else root.ShellInit = api;

  if (typeof module === 'undefined' && typeof document !== 'undefined' && typeof fetch === 'function') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { api.init('workbench-view'); });
    } else {
      api.init('workbench-view');
    }
  }
})(typeof window !== 'undefined' ? window : globalThis);