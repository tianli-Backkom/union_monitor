const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const M = require('../web/core.js');

const app = fs.readFileSync(path.join(__dirname, '..', 'web', 'app.js'), 'utf8');

test('P-004: searchPRs narrows the list but the analysis set is unchanged', () => {
  const prs = [
    { number: 1, title: 'fix e2e gate', author: 'alice', state: 'open', batches: [{ sha: 'abc' }, { sha: 'def' }] },
    { number: 2, title: 'doc update', author: 'bob', state: 'merged', batches: [{ sha: 'xyz' }] },
  ];
  const analysis = M.filterPRs(prs, { state: '' });
  assert.equal(analysis.length, 2);
  const list = M.searchPRs(analysis, 'e2e');
  assert.deepEqual(list.map(p => p.number), [1]);
  // The KPI source (S) must not shrink when the search (L) narrows.
  assert.equal(M.aggregate(analysis).e2e.n, M.aggregate(prs).e2e.n);
});

test('P-004: filterPRs no longer consumes the query (search is a separate stage)', () => {
  const prs = [{ number: 1, title: 'hello', state: 'open', batches: [] }];
  assert.equal(M.filterPRs(prs, { query: 'hello' }).length, 1);
  assert.equal(M.filterPRs(prs, { query: 'nomatch' }).length, 1);
});

test('P-004: searchPRs matches number/title/author/sha and ignores empty query', () => {
  const prs = [{ number: 7, title: 't', author: 'x', state: 'open', batches: [{ sha: 'deadbeef' }] }];
  assert.equal(M.searchPRs(prs, '7').length, 1);
  assert.equal(M.searchPRs(prs, 'dead').length, 1);
  assert.equal(M.searchPRs(prs, 'x').length, 1);
  assert.equal(M.searchPRs(prs, '').length, 1);
  assert.equal(M.searchPRs(prs, 'zzz').length, 0);
});

test('P-004: app.js drives KPI/trend from analysisSet and only the list from search', () => {
  assert.match(app, /const f=readFilters\(\),analysisSet=Metrics\.filterPRs\(snapshot\.prs,f\)/);
  assert.match(app, /filtered=Metrics\.sortPRs\(Metrics\.searchPRs\(analysisSet,f\.query\),prSort\)/);
  assert.match(app, /batchList=entity==='batches'\?buildBatchList\(analysisSet,f\.query\):\[\]/);
  assert.match(app, /\$\('kpis'\)\.innerHTML=kpiHTML\(analysisSet\)/);
  assert.match(app, /drawTrend\(analysisSet\)/);
  assert.match(app, /const pct=analysisSet\.length\?s\.e2e\.n\/analysisSet\.length/);
});