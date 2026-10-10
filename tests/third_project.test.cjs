const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Catalog = require('../web/catalog.js');
const Workbench = require('../web/workbench.js');

const base = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'catalog.json'), 'utf8'));

function thirdProjectCatalog() {
  const data = JSON.parse(JSON.stringify(base));
  data.projects.push({
    project_id: 'acme',
    display_name: 'Acme CI',
    enabled: true,
    collector: 'github-actions-v1',
    metric_profile: 'triton-commit-attempt-v1',
    view_profile: 'commit-attempt-v1',
    window: { time_basis: 'batch_started_at', hours: 96 },
    timeout_minutes: 45,
    repositories: [{ repository_id: 'github:acme/eng-dashboard', target_branches: ['main'] }],
  });
  return data;
}

test('P-015: shell catalog parsing enumerates a third project by configuration', () => {
  const catalog = Catalog.parseCatalog(thirdProjectCatalog());
  assert.deepEqual(
    Catalog.enabledProjects(catalog).map(p => p.project_id),
    ['ubs', 'triton', 'acme'],
  );
  assert.deepEqual(
    Catalog.projectRepositories(catalog, 'acme').map(r => r.repository_id),
    ['github:acme/eng-dashboard'],
  );
  assert.equal(Catalog.projectById(catalog, 'acme').window_hours, undefined);
  assert.equal(Catalog.projectById(catalog, 'acme').window.hours, 96);
});

test('P-015: workbench renders a card per enabled project without id branching', () => {
  const cards = Workbench.projectCards(thirdProjectCatalog(), {});
  assert.deepEqual(cards.map(c => c.project_id), ['ubs', 'triton', 'acme']);
  const acme = cards.find(c => c.project_id === 'acme');
  assert.equal(acme.display_name, 'Acme CI');
  assert.equal(acme.repository_count, 1);
  assert.equal(acme.window_hours, 96);
});