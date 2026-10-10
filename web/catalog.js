/* Catalog parsing for the dashboard shell (T-002, P-002, P-015).

   The catalog is the single source of truth for projects, repositories and
   capabilities. The shell reads `enabled` projects and renders one project
   selector and a fixed task navigation; it never branches on a hardcoded
   project id, so a third project is added by configuration only.

   Legacy short names (e.g. ``ubs-engine``) resolve to a stable repository id
   (``gitcode:openeuler/ubs-engine``) as an explicit alias. */
(function (root) {
  function parseCatalog(data) {
    if (!data || typeof data !== 'object') throw new Error('catalog must be an object');
    if (data.schema_version !== 1) throw new Error('unsupported catalog schema_version');
    if (!Array.isArray(data.projects)) throw new Error('catalog missing projects');
    return data;
  }

  function enabledProjects(catalog) {
    return (catalog.projects || []).filter(function (p) { return p.enabled; });
  }

  function projectById(catalog, id) {
    return (catalog.projects || []).find(function (p) { return p.project_id === id; }) || null;
  }

  function repositoryTail(repositoryId) {
    const slash = repositoryId.lastIndexOf('/');
    return slash === -1 ? repositoryId : repositoryId.slice(slash + 1);
  }

  /* Legacy name -> stable repository id: exact id match or the trailing
     owner/repository segment, case-preserved. */
  function findRepositoryId(catalog, name) {
    for (const project of catalog.projects || []) {
      for (const repo of project.repositories || []) {
        if (repo.repository_id === name || repositoryTail(repo.repository_id) === name) {
          return repo.repository_id;
        }
      }
    }
    return null;
  }

  function repositoryBranches(catalog, projectId, repositoryId) {
    const project = projectById(catalog, projectId);
    if (!project) return [];
    const repo = (project.repositories || []).find(function (r) { return r.repository_id === repositoryId; });
    return repo && Array.isArray(repo.target_branches) ? repo.target_branches : [];
  }

  function capabilitiesFor(catalog, projectId) {
    const project = projectById(catalog, projectId);
    if (!project) return [];
    const view = (catalog.view_profiles || {})[project.view_profile] || {};
    return Array.isArray(view.capabilities) ? view.capabilities : [];
  }

  function hasCapability(catalog, projectId, capability) {
    return capabilitiesFor(catalog, projectId).indexOf(capability) !== -1;
  }

  function projectRepositories(catalog, projectId) {
    const project = projectById(catalog, projectId);
    return project ? (project.repositories || []) : [];
  }

  function sourceInstanceBaseUrl(catalog, sourceInstanceId) {
    const instance = (catalog.source_instances || {})[sourceInstanceId];
    return instance ? instance.base_url : null;
  }

  const api = {
    parseCatalog,
    enabledProjects,
    projectById,
    repositoryTail,
    findRepositoryId,
    repositoryBranches,
    capabilitiesFor,
    hasCapability,
    projectRepositories,
    sourceInstanceBaseUrl,
  };
  if (typeof module !== 'undefined') module.exports = api;
  else root.Catalog = api;
})(typeof window !== 'undefined' ? window : globalThis);