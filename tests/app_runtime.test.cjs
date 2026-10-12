const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createApp } = require('./helpers/app-harness.cjs');

test('project Triton route opens its available trend view rather than the workbench', () => {
  const app = createApp();
  app.run("navigate('#projects/triton/trends')");
  assert.equal(app.element('triton-view').hidden, false);
  assert.equal(app.element('workbench-view').hidden, true);
  assert.match(app.context.document.title, /Triton/);
});

test('project UBS repository route opens the matching repository rather than the workbench', () => {
  const app = createApp();
  app.run("navigate('#projects/ubs/overview?repository=gitcode%3Aopeneuler%2Fubs-comm')");
  assert.equal(app.element('ubs-repo-view').hidden, false);
  assert.equal(app.run('currentRepository'), 'ubs-comm');
});

test('unsupported project task and foreign repository are explicit, without borrowing another project view', () => {
  const app = createApp();
  for (const hash of ['#projects/triton/quality', '#projects/acme/overview', '#projects/ubs/overview?repository=github%3Aforeign%2Fubs-engine']) {
    app.run(`navigate(${JSON.stringify(hash)})`);
    assert.equal(app.element('workbench-view').hidden, true);
    assert.equal(app.element('triton-view').hidden, true);
    assert.equal(app.element('ubs-view').hidden, true);
    assert.equal(app.element('project-task-view').hidden, false);
    assert.match(app.element('project-task-view').innerHTML, /未提供|不支持|未找到/);
  }
});

test('unknown project task and unsupported all-repository task never fall back to a different scope', () => {
  const app = createApp();
  for (const hash of ['#projects/triton/metrics', '#projects/ubs/quality?repository=all', '#projects/ubs/overview?repository=ubs-engine&repository=ubs-comm']) {
    app.run(`navigate(${JSON.stringify(hash)})`);
    assert.equal(app.element('ubs-view').hidden, true);
    assert.equal(app.element('ubs-repo-view').hidden, true);
    assert.equal(app.element('project-task-view').hidden, false);
    assert.match(app.element('project-task-view').innerHTML, /未提供|不支持|未找到/);
  }
});

test('old and new route transitions leave only one view visible', () => {
  const app = createApp();
  app.run("navigate('#workbench');navigate('#triton')");
  assert.equal(app.element('workbench-view').hidden, true);
  assert.equal(app.element('triton-view').hidden, false);
  app.run("navigate('#workbench');navigate('#ubs')");
  assert.equal(app.element('workbench-view').hidden, true);
  assert.equal(app.element('ubs-view').hidden, false);
});

test('workbench transition closes a PR detail and clears bound entity references', () => {
  const app = createApp();
  app.element('detail').open = true;
  app.run("detailPR={number:1};detailRepo='ubs-engine';detailSnapshot={meta:{repository:'openeuler/ubs-engine'}};navigate('#workbench')");
  assert.equal(app.element('detail').open, false);
  assert.equal(app.run('detailPR'), null);
  assert.equal(app.run('detailRepo'), null);
  assert.equal(app.run('detailSnapshot'), null);
});

test('legacy context navigation clears detail references synchronously, before the browser close event', () => {
  const app = createApp();
  app.element('detail').open = true;
  app.run("detailPR={number:1};detailRepo='ubs-engine';detailSnapshot={meta:{repository:'openeuler/ubs-engine'}};navigate('#method')");
  assert.equal(app.element('detail').open, false);
  assert.equal(app.run('detailPR'), null);
  assert.equal(app.run('detailRepo'), null);
  assert.equal(app.run('detailSnapshot'), null);
});

test('leaving the active Triton view invokes its owned resource cleanup', () => {
  const app = createApp();
  let deactivated = 0;
  app.context.window.TritonView = { deactivate() { deactivated++; } };
  app.run("navigate('#triton');navigate('#workbench')");
  assert.equal(deactivated, 1);
});

test('valid zero E2E is not a quality issue, while a missing representative remains an issue', () => {
  const app = createApp();
  app.run("repositoryIndex={generated_at:'2026-10-11T00:00:00Z'};renderAttention([{number:1,issues:[],batches:[{number:1,url:'t/1',eligible:true,e2e_ms:0,status:'success',children:[],issues:[]}]}],[])");
  assert.match(app.element('attention').innerHTML, /<strong>0<\/strong><span>数据质量问题/);
  app.run("renderAttention([{number:2,issues:[],batches:[]}],[])");
  assert.match(app.element('attention').innerHTML, /<strong>1<\/strong><span>数据质量问题/);
});

test('data read timeout covers a stalled JSON body and aborts that request', async () => {
  let expire;
  let signal;
  const app = createApp({
    fetch: async (_url, options) => { signal = options.signal; return { ok: true, json: () => new Promise(() => {}) }; },
    setTimeout(callback) { expire = callback; return 1; }, clearTimeout() {},
  });
  // Run the real fetch callsite as well as its timeout wrapper.
  const reading = app.run("readJSON('data/triton.json','Triton 数据')");
  await Promise.resolve(); await Promise.resolve();
  expire();
  await assert.rejects(reading, /读取超时/);
  assert.equal(signal.aborted, true);
});

test('a failed reread preserves the current valid snapshot and states that it is unchanged', async () => {
  const app = createApp({ fetch: async () => ({ ok: true, json: async () => { throw Error('broken body'); } }) });
  app.run("repositoryIndex={generated_at:'2026-10-11T00:00:00Z',start_ms:1,end_ms:2,repositories:[]};ubsStatus='ok';window.tritonPayload={collected_at:'2026-10-11T00:00:00Z',batches:[]};navigate('#ubs')");
  const previous = app.run('repositoryIndex');
  await app.run('load()');
  assert.equal(app.run('repositoryIndex'), previous);
  assert.equal(app.element('ubs-view').hidden, false);
  assert.match(app.element('loading').textContent, /重新加载快照失败.*数据未更新/);
});

test('workbench reports unavailable task/concern metadata honestly instead of fabricated failed tasks or zero concerns', () => {
  const app = createApp();
  app.run("navigate('#workbench')");
  const html = app.element('workbench-view').innerHTML;
  assert.match(html, /未提供|尚未接入/);
  assert.doesNotMatch(html, /本轮任务.*失败|当前没有需要关注的记录/);
});

test('a repository reread failure keeps its previous validated snapshot available for detail', async () => {
  const app = createApp({ fetch: async url => ({ ok: true, json: async () => {
    if (url.includes('repos/')) throw Error('repository body failed');
    if (url.includes('triton')) return { batches: [] };
    return { generated_at: '2026-10-11T00:00:00Z', start_ms: 3, end_ms: 4, repositories: [{ name: 'ubs-engine', repository: 'openeuler/ubs-engine', snapshot: 'repos/ubs-engine.json', status: 'success' }] };
  } }) });
  app.context.location.hash = '#workbench';
  app.run("repositorySnapshots={'ubs-engine':{meta:{repository:'openeuler/ubs-engine',start_ms:1,end_ms:2,collected_at:'2026-10-10T00:00:00Z'},prs:[]}}");
  const prior = app.run("repositorySnapshots['ubs-engine']");
  await app.run('load()');
  assert.equal(app.run("repositorySnapshots['ubs-engine']"), prior);
  assert.equal(app.run('repositoryIndex.repositories[0].status'), 'failed');
  assert.equal(app.run('Metrics.repositoryRows(repositoryIndex,repositorySnapshots)[0].included'), false);
});

test('workbench reload shows the loaded snapshots without claiming collection task success', async () => {
  const app = createApp({ fetch: async url => ({ ok: true, json: async () => url.includes('triton')
    ? { collected_at: '2026-10-11T00:00:00Z', batches: [] }
    : { generated_at: '2026-10-11T00:00:00Z', start_ms: 1, end_ms: 2, repositories: [] } }) });
  app.context.location.hash = '#workbench';
  app.run("navigate('#workbench')");
  await app.run('load()');
  await Promise.resolve();
  assert.match(app.element('workbench-view').innerHTML, /2026-10-11|2026\/10\/11/);
  assert.match(app.element('workbench-view').innerHTML, /快照.*读取|读取.*快照/);
  assert.doesNotMatch(app.element('workbench-view').innerHTML, /本轮任务.*成功|当前没有需要关注的记录/);
});

test('mobile layout keeps Triton result and duration columns in a module scrolling region', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/style.css'), 'utf8');
  assert.doesNotMatch(css, /\.row-main>:nth-child\(4\),\.row-main>:nth-child\(6\)\{display:none\}/);
  assert.match(css, /\.rows\{[^}]*overflow-x:auto/);
});

test('bootstrap cannot overwrite the truthful workbench with a missing release report', () => {
  const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
  assert.doesNotMatch(html, /<script src="shell-init.js" defer>/);
});
