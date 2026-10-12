const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Run the real view against bounded DOM/timer boundaries. Browser gates test
// the rendered layout and focus; these checks inspect its actual markup/state.
function viewHarness() {
  const nodes = new Map(), documentListeners = new Set(), resizeListeners = new Set(), intervals = new Set(), downloads = [];
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {
      selector, innerHTML:'', textContent:'', value:'', hidden:false, style:{}, dataset:{}, clientWidth:900,
      isConnected:true, children:[{}], classList:{toggle(){},contains(){return false;}},
      querySelectorAll(){return [];}, querySelector(){return null;}, contains(){return false;},
      captures:new Set(),
      setAttribute(name,value){this[name]=value;}, getBoundingClientRect(){return {x:0,y:0,left:0,width:900,height:370};},
      focus(){}, setPointerCapture(id){this.captures.add(id);}, releasePointerCapture(id){this.captures.delete(id);},
    });
    return nodes.get(selector);
  };
  const container = node('container');
  container.querySelector = node;
  const context = {
    ...require('../web/triton-core.js'), Units:require('../web/units.js'), Date, Intl, Blob,
    Metrics:{async saveCsv(rows,name){downloads.push({name,rows});return {mode:'saved',name,url:'/exports/'+name};}},
    URL:{createObjectURL(blob){downloads.push({blob});return 'blob:qualifications';},revokeObjectURL(){}},
    document:{activeElement:null,getElementById:node,createElement(){return {click(){downloads[downloads.length-1].name=this.download;}};},addEventListener(_e,f){documentListeners.add(f);},removeEventListener(_e,f){documentListeners.delete(f);}},
    addEventListener(_e,f){resizeListeners.add(f);},removeEventListener(_e,f){resizeListeners.delete(f);},
    setTimeout(){return 1;},clearTimeout(){},setInterval(f){intervals.add(f);return f;},clearInterval(f){intervals.delete(f);},
  };
  context.window = context;
  vm.runInNewContext(fs.readFileSync(require.resolve('../web/triton-view.js'),'utf8'),context);
  return {view:context.TritonView,container,node,documentListeners,resizeListeners,intervals,downloads};
}

function sample() {
  const batches = Array.from({length:10},(_,i)=>({id:i===9?'failed-long':'batch-'+i,pr:i+1,title:'Example',base_branch:'main',
    sha:'abc',status:i===9?'failure':'success',duration_seconds:i===9?2000:600,
    start_at:'2026-10-10T01:00:00Z',end_at:'2026-10-10T01:33:20Z',missing:[],workflows:[],npu_jobs:[],
    e2e_sample_eligible:true,pr_url:'https://github.com/example/repo/pull/'+(i+1)}));
  batches.push({id:'unresolved',pr:null,title:'未关联',base_branch:'未知目标分支',sha:'def',status:'failure',duration_seconds:5,
    start_at:'2026-10-10T01:00:00Z',end_at:'2026-10-10T01:00:05Z',missing:['未可靠关联 PR'],
    e2e_sample_eligible:false,e2e_exclusion_reason:'unresolved_pr_batch_identity',workflows:[{id:123,attempt:1,jobs:[]}],npu_jobs:[]});
  return {window_start:'2026-10-10T00:00:00Z',window_end:'2026-10-11T00:00:00Z',collected_at:'2026-10-11T00:01:00Z',batches};
}

test('real attention markup renders a failed slow batch once with multiple reasons', () => {
  const h=viewHarness();h.view.render(sample(),h.container);
  const markup=h.node('[data-role="attention"]').innerHTML;
  assert.equal((markup.match(/<article[^>]*id="triton-batch-[^"]*-failed-long"/g)||[]).length,1);
  assert.match(markup,/耗时偏长/);
  assert.match(markup,/失败/);
});

test('real unknown-PR markup has a run identity and never a fake PR hyperlink', () => {
  const h=viewHarness();h.view.render(sample(),h.container);
  const markup=h.node('[data-role="attention"]').innerHTML;
  assert.doesNotMatch(markup,/href="#"/);
  assert.match(markup,/Run #123/);
  assert.match(markup,/E2E 排除/);
});

test('deactivation closes the card and clears resources, while remount restores query state once', () => {
  const h=viewHarness(),data=sample();h.view.render(data,h.container);
  h.node('[data-role="search"]').value='Example';
  h.node('[data-role="tip"]').style.display='block';
  assert.equal(typeof h.view.deactivate,'function');
  h.view.deactivate();
  assert.equal(h.node('[data-role="tip"]').style.display,'none');
  assert.equal(h.documentListeners.size,0);assert.equal(h.resizeListeners.size,0);assert.equal(h.intervals.size,0);
  h.node('[data-role="search"]').value='';h.view.render(data,h.container);
  assert.equal(h.node('[data-role="search"]').value,'Example');
  assert.equal(h.documentListeners.size,1);assert.equal(h.resizeListeners.size,1);assert.equal(h.intervals.size,1);
  h.view.render(data,h.container);
  assert.equal(h.documentListeners.size,1);assert.equal(h.intervals.size,1);
});

test('record export retains observations in the 16-column CSV and persists qualification metadata separately', async () => {
  const h=viewHarness();h.view.render(sample(),h.container);
  await h.node('[data-role="exportBatches"]').onclick();
  assert.equal(h.downloads.length,2);
  assert.equal(h.downloads[0].rows[0].length,16);
  assert.equal(h.downloads[0].rows.length,12);
  assert.equal(h.downloads[1].name,'triton-qualifications-v1.json');
  const metadata=JSON.parse(await h.downloads[1].blob.text());
  assert.equal(metadata.schema_version,1);
  assert.equal(metadata.batches.length,11);
  assert.equal(metadata.batches.find(batch=>batch.id==='unresolved').e2e_sample_eligible,false);
});

test('deactivation releases a navigator pointer that was still captured mid-drag', () => {
  const h=viewHarness();h.view.render(sample(),h.container);
  const navigator=h.node('[data-role="navigator"]');
  navigator.onpointerdown({preventDefault(){},pointerId:42,clientX:450,target:{dataset:{drag:'window'}}});
  assert.equal(navigator.captures.size,1);
  h.view.deactivate();
  assert.equal(navigator.captures.size,0);
  assert.equal(navigator.onpointermove,null);
});
