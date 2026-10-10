const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Catalog = require('../web/catalog.js');

const catalogJson = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'catalog.json'), 'utf8'));
const catalog = Catalog.parseCatalog(catalogJson);

test('enabledProjects returns the two real projects', () => {
  assert.deepEqual(Catalog.enabledProjects(catalog).map(p => p.project_id), ['ubs', 'triton']);
});

test('projectById finds a project by stable id', () => {
  assert.equal(Catalog.projectById(catalog, 'ubs').display_name, 'openEuler UBS');
  assert.equal(Catalog.projectById(catalog, 'triton').display_name, 'Triton-Ascend');
  assert.equal(Catalog.projectById(catalog, 'nope'), null);
});

test('capabilities come from the referenced view profile', () => {
  assert.deepEqual(Catalog.capabilitiesFor(catalog, 'ubs'), [
    'repository_comparison', 'pr_lifecycle', 'task_breakdown', 'evidence_detail', 'csv',
  ]);
  assert.ok(Catalog.hasCapability(catalog, 'ubs', 'pr_lifecycle'));
  assert.ok(!Catalog.hasCapability(catalog, 'ubs', 'batch_trend'));
  assert.deepEqual(Catalog.capabilitiesFor(catalog, 'nope'), []);
});

test('legacy short names resolve to stable repository ids', () => {
  assert.equal(Catalog.findRepositoryId(catalog, 'ubs-engine'), 'gitcode:openeuler/ubs-engine');
  assert.equal(Catalog.findRepositoryId(catalog, 'OmniStateStore'), 'gitcode:openeuler/OmniStateStore');
  assert.equal(Catalog.findRepositoryId(catalog, 'gitcode:openeuler/ubs-comm'), 'gitcode:openeuler/ubs-comm');
  assert.equal(Catalog.findRepositoryId(catalog, 'triton-ascend'), 'github:triton-lang/triton-ascend');
  assert.equal(Catalog.findRepositoryId(catalog, 'missing'), null);
});

test('repositoryTail splits without lowercasing', () => {
  assert.equal(Catalog.repositoryTail('gitcode:openeuler/OmniStateStore'), 'OmniStateStore');
  assert.equal(Catalog.repositoryTail('github:triton-lang/triton-ascend'), 'triton-ascend');
});

test('target branches are exposed per repository', () => {
  assert.deepEqual(Catalog.repositoryBranches(catalog, 'ubs', 'gitcode:openeuler/ubs-engine'), ['master']);
  assert.deepEqual(Catalog.repositoryBranches(catalog, 'triton', 'github:triton-lang/triton-ascend'), ['main', 'main-dev']);
});

test('source instance base urls are reachable through the catalog', () => {
  assert.equal(Catalog.sourceInstanceBaseUrl(catalog, 'gitcode'), 'https://gitcode.com');
  assert.equal(Catalog.sourceInstanceBaseUrl(catalog, 'github'), 'https://github.com');
});

test('parseCatalog rejects malformed input', () => {
  assert.throws(() => Catalog.parseCatalog(null), /object/);
  assert.throws(() => Catalog.parseCatalog({ schema_version: 2, projects: [] }), /schema_version/);
  assert.throws(() => Catalog.parseCatalog({ schema_version: 1 }), /projects/);
});