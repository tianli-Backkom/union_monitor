const { test } = require('node:test');
const assert = require('node:assert/strict');
const R = require('../web/router.js');

test('parseRoute parses the new workbench and project routes', () => {
  assert.deepEqual(R.parseRoute('#workbench'), { view: 'workbench', query: {} });
  assert.deepEqual(R.parseRoute('#projects/ubs/overview'), { view: 'projects', project: 'ubs', task: 'overview', query: {} });
  assert.deepEqual(R.parseRoute('#projects/triton/trends'), { view: 'projects', project: 'triton', task: 'trends', query: {} });
  assert.equal(R.parseRoute('#ubs'), null);
  assert.equal(R.parseRoute('#nope'), null);
});

test('parseRoute decodes query params including nested entity values', () => {
  const route = R.parseRoute('#projects/ubs/records?repository=gitcode%3Aopeneuler%2Fubs-engine&entity=batches&q=248&sort=start-desc&page=1');
  assert.equal(route.project, 'ubs');
  assert.equal(route.task, 'records');
  assert.equal(route.query.repository, 'gitcode:openeuler/ubs-engine');
  assert.equal(route.query.entity, 'batches');
  assert.equal(route.query.q, '248');
  assert.equal(route.query.sort, 'start-desc');
  assert.equal(route.query.page, '1');
});

test('parseQuery aggregates repeated keys and ignores empties', () => {
  assert.deepEqual(R.parseQuery('branches=main&branches=main-dev&from=x'), {
    branches: ['main', 'main-dev'],
    from: 'x',
  });
  assert.deepEqual(R.parseQuery(''), {});
  assert.deepEqual(R.parseQuery('a&b='), { a: '', b: '' });
});

test('formatRoute emits canonical hashes and round-trips through parseRoute', () => {
  const route = { view: 'projects', project: 'ubs', task: 'records', query: { repository: 'gitcode:openeuler/ubs-engine', entity: 'batches', page: '1' } };
  const hash = R.formatRoute(route);
  assert.equal(hash, '#projects/ubs/records?repository=gitcode%3Aopeneuler%2Fubs-engine&entity=batches&page=1');
  assert.deepEqual(R.parseRoute(hash), route);
  assert.equal(R.formatRoute({ view: 'workbench' }), '#workbench');
  assert.equal(R.formatRoute(null), '#workbench');
});

test('legacyIntent maps every legacy hash to its intended new route', () => {
  assert.deepEqual(R.legacyIntent('#ubs'), { view: 'projects', project: 'ubs', task: 'overview' });
  assert.deepEqual(R.legacyIntent('#repositories'), { view: 'projects', project: 'ubs', task: 'overview' });
  assert.deepEqual(R.legacyIntent('#ubs/repo/ubs-comm'), { view: 'projects', project: 'ubs', task: 'overview', repository: 'ubs-comm' });
  assert.deepEqual(R.legacyIntent('#ubs/repo/ubs-comm/quality'), { view: 'projects', project: 'ubs', task: 'quality', repository: 'ubs-comm' });
  assert.deepEqual(R.legacyIntent('#overview'), { view: 'projects', project: 'ubs', task: 'overview', repository: 'ubs-engine' });
  assert.deepEqual(R.legacyIntent('#prs'), { view: 'projects', project: 'ubs', task: 'records', repository: 'ubs-engine', entity: 'batches' });
  assert.deepEqual(R.legacyIntent('#quality'), { view: 'projects', project: 'ubs', task: 'quality', repository: 'ubs-engine' });
  assert.deepEqual(R.legacyIntent('#triton'), { view: 'projects', project: 'triton', task: 'trends' });
  assert.deepEqual(R.legacyIntent('#method'), { view: 'projects', project: null, task: 'method' });
  assert.deepEqual(R.legacyIntent('#repo/ham'), { view: 'projects', project: 'ubs', task: 'overview', repository: 'ham' });
  assert.deepEqual(R.legacyIntent('#repo/ham/method'), { view: 'projects', project: 'ubs', task: 'method', repository: 'ham' });
});

test('legacyIntent leaves the new scheme untouched and unknown hashes unmapped', () => {
  assert.equal(R.legacyIntent('#workbench'), null);
  assert.equal(R.legacyIntent('#projects/ubs/overview'), null);
  assert.equal(R.legacyIntent('#definitely-unknown'), null);
});