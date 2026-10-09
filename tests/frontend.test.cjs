const {test}=require('node:test');const assert=require('node:assert/strict');const M=require('../web/core.js');
const fs=require('node:fs'),path=require('node:path');
const batch=(number,e2e_ms,eligible=true,children=[])=>({number,url:`trigger/${number}`,e2e_ms,eligible,children,status:'failure'});
test('one representative per PR gives mean25 P9029',()=>{const a={batches:[batch(1,10),batch(2,30)]},b={batches:[batch(3,20)]};assert.deepEqual(M.aggregate([a,b]).e2e,{n:2,mean:25,p90:29});});
test('ties, exclusions, missing tasks and no valid batch',()=>{const task={kind:'x86',url:'x/1',result:'SUCCESS',association_valid:true,total_ms:100};const bs=[batch(1,10,true,[task]),batch(2,30),batch(3,30),batch(4,100,false)];assert.equal(M.metrics(bs).representative_batch_number,3);assert.equal(M.metrics(bs).x86.total_ms,null);assert.equal(M.metrics([]).e2e_ms,null);});
test('task values come from same representative and filters preserve batches',()=>{const task=t=>({kind:'x86',url:'x/'+t,result:'SUCCESS',association_valid:true,total_ms:t});const p={number:1,state:'open',batches:[batch(1,10,true,[task(100)]),batch(2,30,true,[task(20)])]};assert.equal(M.aggregate([p]).x86.total.mean,20);assert.equal(M.filterPRs([p],{state:'open'})[0],p);assert.equal(M.filterPRs([p],{state:'merged'}).length,0);assert.equal(M.metrics(p.batches).representative_batch_number,2);});
test('percentile, empty and CSV formula escaping',()=>{assert.equal(M.stats([0,100,200,300]).p90,270);assert.equal(M.stats([]).mean,null);assert.ok(M.csv([['=1+1','a"b']]).includes("'=1+1"));});
test('frontend matches every persisted PR representative',()=>{const s=require('../data/snapshot.json');for(const p of s.prs)assert.deepEqual(M.metrics(p.batches),p.metrics);});
test('CSV exporter is available to browser and Node callers',()=>{assert.equal(typeof M.saveCsv,'function');});
test('static Pages export downloads a Blob without posting to the local API',async()=>{
 let fetches=0,clicked=false,blob,urlRevoked;
 const env={location:{hostname:'tianli-backkom.github.io'},fetch:async()=>{fetches++;},Blob,URL:{createObjectURL:value=>(blob=value,'blob:csv'),revokeObjectURL:value=>{urlRevoked=value}},document:{createElement:()=>({click(){clicked=true}})}};
 const result=await M.saveCsv([['仓库','PR'],['openeuler/ubs-engine',1]],'pr-summary.csv',env);
 assert.equal(fetches,0);assert.equal(clicked,true);assert.equal(urlRevoked,'blob:csv');assert.equal(result.mode,'download');assert.match(await blob.text(),/openeuler\/ubs-engine/);
});
test('localhost export posts CSV to the local save endpoint',async()=>{
 let request;const env={location:{hostname:'localhost'},fetch:async(url,options)=>(request={url,options},{ok:true,json:async()=>({url:'/exports/a.csv',name:'a.csv'})})};
 const result=await M.saveCsv([['仓库'],['openeuler/ubs-engine']],'a.csv',env);
 assert.equal(request.url,'/api/export');assert.equal(request.options.method,'POST');assert.match(request.options.body,/openeuler\/ubs-engine/);assert.equal(result.mode,'saved');
});
test('dashboard routes every CSV download through the environment-aware exporter',()=>{const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');assert.match(source,/Metrics\.saveCsv\(rows,name\)/);});
test('PR sorting has deterministic E2E, execution-count and creation orders',()=>{
 const p=(number,e2e,batches,created)=>({number,created_ms:created,batches:Array.from({length:batches},(_,i)=>({number:i+1,url:`t/${number}/${i}`,eligible:true,e2e_ms:e2e,children:[]}))});
 const slow=p(1,30,2,10),many=p(2,20,5,20),newer=p(3,20,1,30);
 assert.deepEqual(M.sortPRs([many,newer,slow],'e2e').map(x=>x.number),[1,3,2]);
 assert.deepEqual(M.sortPRs([slow,newer,many],'batches').map(x=>x.number),[2,1,3]);
 assert.deepEqual(M.sortPRs([slow,many,newer],'created').map(x=>x.number),[3,2,1]);
});
test('createReloadGate: only the newest generation is current',()=>{
 const gate=M.createReloadGate();
 const g1=gate.begin();
 assert.equal(gate.isCurrent(g1),true);
 const g2=gate.begin();
 assert.equal(gate.isCurrent(g1),false,'a stale generation must be discarded');
 assert.equal(gate.isCurrent(g2),true);
 assert.equal(gate.isCurrent(0),false,'unknown generations never pass');
 assert.equal(gate.isCurrent(999),false);
 assert.ok(gate.begin()>g2,'generations strictly increase');
});
test('app load() guards every await boundary with the reload gate',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
 assert.match(source,/const gen=reloadGate\.begin\(\)/,'load() must open a generation');
 const guards=(source.match(/if\(!reloadGate\.isCurrent\(gen\)\)return;/g)||[]).length;
 assert.ok(guards>=3,'index, snapshot commit and error paths must all be guarded, found '+guards);
  assert.match(source,/if\(reloadGate\.isCurrent\(gen\)\)\{window\.tritonPayload=d;tritonStatus='ok'\}/,'the Triton payload commit must be generation-checked');
});
test('reload failure keeps the previous snapshot visible with its collection time',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
 assert.match(source,/function freshnessText\(\)/,'collection-time text is factored out for reuse');
 assert.match(source,/重新加载快照失败：'\+e\.message\+'。当前仍显示 '\+freshnessText\(\)\+' 采集的快照/,'the failure notice must name the still-displayed snapshot time');
  const failPath=source.slice(source.indexOf("}catch(e){"));
  const hasDataBranch=failPath.indexOf('if(repositoryIndex){');
  assert.ok(hasDataBranch>-1,'the has-snapshot branch must come first in the catch');
  const branchEnd=failPath.indexOf('return;',hasDataBranch);
  assert.ok(branchEnd>-1,'the has-snapshot branch must return before the first-load fallback runs');
  const branch=failPath.slice(hasDataBranch,branchEnd);
  assert.ok(branch.includes('navigate(location.hash);'),'the has-snapshot branch re-renders the current view');
  assert.ok(branch.indexOf('navigate(location.hash);')<branch.indexOf("$('loading').hidden=false"),'the failure banner must be revealed after the re-render so the render path cannot hide it again');
  const fallback=failPath.slice(branchEnd);
  assert.ok(fallback.includes('navigate(location.hash);'),'REQ-010: the first-load fallback must still route the current view instead of hiding it');
  assert.ok(!failPath.includes("for(const id of ['ubs-view'"),'REQ-010: a UBS index failure must not hide the triton and method views');
});

test('navigation or reload closes a stale PR detail and clears its reference',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
 assert.match(source,/detailRepo=null,/,'module state must track the repository a detail belongs to');
 assert.match(source,/detailRepo=currentRepository;/,'openDetail must record the repository the detail was opened from');
 assert.ok(source.includes("(detailPR||$('detail').open)&&(domain!=='ubs'||!repo||currentRepository!==detailRepo)"),'context-changing navigation (domain, repository or leaving the repo view) must close the detail dialog');
 assert.ok(source.includes("reloadGate.begin();$('detail').close();"),'a reload attempt must close the open detail at start, before fetching');
 assert.ok(source.includes("addEventListener('close',()=>{if(!$('detail').open){detailPR=null;detailSnapshot=null;}})"),'any dialog close (button, overlay, Esc) must clear the stale detail reference and snapshot binding');
});

test('detail CSV export is bound to the detail entity, not the global current repository',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
 assert.match(source,/detailSnapshot=snapshot;/,'openDetail must bind the snapshot the detail was opened from');
 assert.ok(source.includes('detailSnapshot.meta.repository,detailPR.number'),'the batch CSV repository column must come from the detail-bound snapshot');
 assert.ok(source.includes('${detailRepo}-pr-${detailPR.number}-batches.csv'),'the batch CSV filename must use the detail-bound repository');
 assert.ok(source.includes("if(!detailPR||!detailSnapshot){ensureNotice().textContent='无法导出批次：当前没有打开有效的 PR 详情。';return;}"),'a missing detail context must block export with an explanatory notice');
 const start=source.indexOf('function exportBatches');
 const end=source.indexOf('async function load');
 assert.ok(start>-1&&end>start,'exportBatches source found');
 const exportSrc=source.slice(start,end);
  assert.ok(!exportSrc.includes('currentRepository'),'exportBatches must not read the global current repository');
  assert.ok(!exportSrc.includes('snapshot.meta.repository'),'exportBatches must not read the global snapshot');
});

test('REQ-010: the two domains read independently — a UBS index failure cannot block Triton',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
  const tritonStart=source.indexOf('const tritonTask=(async()=>{');
  const ubsStart=source.indexOf("const response=await fetch('data/repositories.json'");
  assert.ok(tritonStart>-1&&ubsStart>-1,'load() must define both domain read tasks');
  assert.ok(tritonStart<ubsStart,'the Triton fetch must start before the UBS index fetch so an index failure can never prevent it');
  assert.ok(source.includes('}),tritonTask]);'),'the success path awaits both domains together');
  assert.ok(!source.includes('window.tritonPayload=null'),'a failed Triton re-read must keep the previous payload visible instead of nulling it');
  assert.ok(source.includes("if(view==='ubs')$('loading').hidden=false;"),'the first-load UBS failure banner only takes over UBS views, leaving #triton usable');
});

test('REQ-010: Triton view states distinguish in-flight, failure and previous data',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
  assert.ok(source.includes('正在读取 Triton 数据…'),'an in-flight state must have its own message (加载中)');
  assert.ok(source.includes("Triton 数据读取失败：'+esc(tritonError||'未知错误')"),'failures must surface the error type instead of an empty/zero state');
  assert.ok(source.includes('Triton 数据重新读取失败：'),'a re-read failure must explain that previous data is still shown');
  assert.ok(source.includes("setAttribute('data-role','tritonError')"),'the re-read failure notice is deduplicated across re-renders');
  assert.ok(source.includes("if(!d||typeof d!=='object'||!Array.isArray(d.batches))throw Error('Triton 数据格式无效')"),'bad Triton JSON shapes are rejected while empty batches stay legal zero data');
});

test('REQ-010: per-repo read failures degrade locally with distinct notices',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
  assert.ok(source.includes("data.meta.repository!==entry.repository"),'a snapshot whose repository does not match its index entry must be rejected (no cross-repo borrowing)');
  assert.ok(source.includes("entry.status='failed';entry.error='快照读取失败：'+error.message"),'a failing repository is marked failed without aborting the other reads');
  assert.ok(source.includes("entry?.status==='failed'?'该仓库'+(entry.error||'数据不可用')+'。其他仓库与 Triton 数据不受影响。'"),'a read-failed repository must be told apart from a never-collected one');
  assert.ok(source.includes('该仓库尚未获取数据，请查看采集状态后运行采集命令。'),'the pending (未获取) notice stays distinct from the failure notice');
  assert.ok(source.includes("?' · 快照读取失败':' · 未获取数据'"),'the footer labels failure and never-collected differently');
  assert.ok(source.includes("$('loading').hidden=!ubs||(cross?!!repositoryIndex:!!snapshot)"),'the overview keeps its status line visible while the index is unread and hides it once data exists');
  assert.ok(source.includes("'仓库索引未读取，UBS 视图暂不可用'"),'a missing index must not be misreported as 未找到仓库');
});

 test('REQ-011: the methodology page renders without waiting for snapshot reads',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
  assert.ok(source.includes('navigate(location.hash);load();'),'the current route must render at startup, before load() fetches any snapshot (AC02: 直接打开#method不隐藏口径正文)');
  assert.ok(source.includes("ubsStatus='loading';tritonStatus='loading';"),'both domains start as loading so a pending read is never reported as failed');
  assert.ok(source.includes("ubsStatus==='failed'?'仓库索引未读取，UBS 视图暂不可用':''"),'the missing-index notice appears only after a failure, not while the read is in flight (AC01/AC03)');
  assert.ok(source.includes("ubsStatus='ok';"),'a successful index read marks the UBS domain ok');
  assert.ok(source.includes("ubsStatus='failed';"),'a failed index read marks the UBS domain failed');
  assert.ok(source.includes("'数据读取中…':'快照未读取'"),'freshness distinguishes in-flight reads from never-read data');
});

test('REQ-016 AC01: a batch whose event_id is not in events stays visible in the detail groups',()=>{
  const b=(n,event_id)=>({number:n,url:`trigger/${n}`,e2e_ms:10,eligible:true,children:[],status:'success',event_id});
  const pr={events:[{id:'e1',kind:'create'},{id:'e2',kind:'push'}],batches:[b(1,'e1'),b(2,'e2'),b(3,'e-unknown')]};
  const groups=M.detailGroups(pr);
  assert.equal(groups.length,3,'two known events plus one unmatched group');
  assert.equal(groups.flatMap(g=>g.batches).length,3,'all three batches are displayed, not two');
  const unmatched=groups.find(g=>g.event.kind==='unmatched');
  assert.ok(unmatched.batches.some(x=>x.url==='trigger/3'),'the mismatched batch is not dropped');
  assert.match(unmatched.reason,/1 批 event_id 不在事件列表/);
});

test('REQ-016 AC02: every batch identity appears exactly once across empty, unknown, missing and duplicate event shapes',()=>{
  const b=(n,event_id)=>({number:n,url:`trigger/${n}`,e2e_ms:10,eligible:true,children:[],status:'success',event_id});
  const identities=pr=>M.detailGroups(pr).flatMap(g=>g.batches).map(x=>x.url).sort();
  const mixed={events:[{id:'e1',kind:'create'}],batches:[b(1,'e1'),b(2,''),b(3,'e-unknown')]};
  assert.deepEqual(identities(mixed),['trigger/1','trigger/2','trigger/3'],'empty event_id and unknown non-empty event_id both stay');
  assert.match(M.detailGroups(mixed)[1].reason,/1 批 event_id 为空，1 批 event_id 不在事件列表/);
  const noEvents={batches:[b(1,'e1'),b(2,'e2')]};
  assert.deepEqual(identities(noEvents),['trigger/1','trigger/2'],'without events all batches fall into the mismatch group');
  const duplicate={events:[{id:'e1',kind:'create'},{id:'e1',kind:'create'}],batches:[b(1,'e1')]};
  assert.equal(M.detailGroups(duplicate).length,1,'duplicate events render one group');
  assert.deepEqual(identities(duplicate),['trigger/1'],'duplicate events never show the batch twice');
});

test('REQ-016 AC03/AC04: unmatched group keeps batch links and the representative; the detail CSV stays the full set',()=>{
  const b=(n,event_id)=>({number:n,url:`trigger/${n}`,e2e_ms:10,eligible:true,children:[],status:'success',event_id});
  const pr={events:[{id:'e1',kind:'create'}],batches:[b(1,'e1'),b(2,'e-unknown')]};
  const unmatched=M.detailGroups(pr).find(g=>g.event.kind==='unmatched');
  assert.ok(unmatched.batches.some(x=>x.url==='trigger/2'),'a mismatched batch stays in its group so openDetail can still mark the representative');
  assert.equal(unmatched.event.time_ms,undefined);
  assert.equal(unmatched.event.sha,undefined);
  const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
  assert.ok(source.includes('for(const b of detailPR.batches)'),'the batch CSV iterates the full detail batch set, independent of grouping');
  assert.ok(source.includes('batchHTML(b,b.url===s.representative_batch_url)'),'representative marking is positional and applies to every group');
});
