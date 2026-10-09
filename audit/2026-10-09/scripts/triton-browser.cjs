/* Audit harness: reads production assets; writes only audit evidence. */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {chromium} = require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1007-641-0_26.1007.641.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const ROOT='D:/ubs_core_monitor', OUT=ROOT+'/audit/2026-10-09';
const BASE='http://127.0.0.1:18765/';
const payload=JSON.parse(fs.readFileSync(ROOT+'/web/data/triton.json','utf8'));
const end=Date.parse(payload.window_end), start=Date.parse(payload.window_start);
const checks=[], consoleErrors=[], screenshots=[];
const role=x=>`[data-role="${x}"]`;
const select=(rows,hours)=>rows.filter(b=>Date.parse(b.start_at)>=Math.max(start,end-hours*3600000)&&Date.parse(b.start_at)<=end);
const pct=(values,q)=>{const v=values.slice().sort((a,b)=>a-b),p=(v.length-1)*q;return v.length?v[Math.floor(p)]+(v[Math.ceil(p)]-v[Math.floor(p)])*(p-Math.floor(p)):null;};
function record(id,label,actual,expected,meta={}){
 const passed=JSON.stringify(actual)===JSON.stringify(expected);
 checks.push({id,label,state:passed?'passed':'failed',actual,expected,...meta});
 console.log(JSON.stringify({id,state:passed?'passed':'failed',actual,expected}));
}
async function shot(page,name){const file=OUT+'/screenshots/'+name+'.png';await page.screenshot({path:file,fullPage:true,animations:'disabled'});await page.screenshot({path:OUT+'/screenshots/'+name+'-viewport.png',animations:'disabled'});screenshots.push(file);return 'screenshots/'+name+'.png';}
async function mount(browser,hash='triton',options={}){
 const ctx=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true,...options});
 const page=await ctx.newPage();page.on('pageerror',e=>consoleErrors.push({url:page.url(),message:e.message}));
 await page.goto(BASE+'#'+hash,{waitUntil:'networkidle'});
 await page.locator(hash==='triton'?role('chart'):'#repositoryRows tr').first().waitFor({state:'visible'});
 return {ctx,page};
}
async function ids(page,kind='chart'){return page.locator(role(kind)+' .mark-hit').evaluateAll(nodes=>nodes.map(n=>+n.dataset.i).sort((a,b)=>a-b));}
function expectedIds(rows){return rows.map(b=>payload.batches.indexOf(b)).sort((a,b)=>a-b);}
async function text(page,r){return page.locator(role(r)).textContent();}
async function getState(page){return {branch:await page.locator(role('branchOptions')+' input:checked').evaluateAll(ns=>ns.map(n=>n.value)),range:await text(page,'selectedRange'),query:await page.locator(role('search')).inputValue(),e2e:await page.locator(role('e2eFilters')+' .active').getAttribute('data-filter'),npu:await page.locator(role('npuFilters')+' .active').getAttribute('data-npu-filter'),listMode:await text(page,'showAll')};}
async function guarded(name,fn){if(process.env.AUDIT_GROUP&&!process.env.AUDIT_GROUP.split(',').includes(name))return;try{await fn();}catch(e){checks.push({id:name,label:name,state:'unverified',reason:e.stack});console.log(JSON.stringify({id:name,error:e.message}));}}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try {
  await guarded('triton-real-controls',async()=>{
   const {ctx,page}=await mount(browser);
   record('T01','Triton 初始批次数',Number(await text(page,'kBatch')),payload.batches.length,{kind:'real'});
   record('T02','初始 E2E 散点身份',await ids(page),expectedIds(payload.batches));
   record('T03','初始 NPU 散点身份',await ids(page,'npuChart'),expectedIds(payload.batches.filter(b=>b.npu_queue_seconds!=null)));
   await shot(page,'triton-desktop-initial');
   await page.locator(role('branchFilter')+' summary').click();
   const branches=await page.locator(role('branchOptions')+' input').evaluateAll(ns=>ns.map(n=>n.value));
   const chosen=branches[0],pool=payload.batches.filter(b=>b.base_branch===chosen);
   await page.locator(role('branchOptions')+' input').first().check();
   record('T04','单分支全局汇总',Number(await text(page,'kBatch')),pool.length);
   record('T05','单分支两图联动',await ids(page),expectedIds(pool));
   if(branches.length>1){await page.locator(role('branchOptions')+' input').nth(1).check();record('T06','多分支集合',Number(await text(page,'kBatch')),payload.batches.filter(b=>branches.slice(0,2).includes(b.base_branch)).length);}
   await page.locator(role('clearBranches')).click();
   record('T07','清除分支恢复全部',Number(await text(page,'kBatch')),payload.batches.length);
   await page.locator(role('showAll')).click();
   const windows=[];
   for(const h of [6,12,24,48,72]){
    await page.locator(`[data-hours="${h}"]`).click();
    const rows=select(payload.batches,h);
    const observed={hours:h,kBatch:Number(await text(page,'kBatch')),listCount:await page.locator(role('attention')+' .row').count(),e2e:await ids(page),npu:await ids(page,'npuChart')};
    const expected={hours:h,kBatch:rows.length,listCount:rows.length,e2e:expectedIds(rows),npu:expectedIds(rows.filter(b=>b.npu_queue_seconds!=null))};
    windows.push({observed,expected});
    record('T08-'+h,'时间窗全页联动 '+h+'h',observed,expected);
   }
   await page.locator('[data-hours="6"]').click();
   await shot(page,'triton-six-hour-mismatch');
   const w6=select(payload.batches,6),p90=pct(w6.filter(b=>['success','failure'].includes(b.status)).map(b=>b.duration_seconds),.9);
   await page.locator('[data-filter="slow"]').click();
   record('T09','偏长阈值使用所选时间窗 P90',await ids(page),expectedIds(w6.filter(b=>b.status!=='running'&&b.duration_seconds!=null&&p90!=null&&b.duration_seconds>=p90)),{selectedP90:p90});
   await page.locator('[data-filter="failure"]').click();
   record('T10','E2E 状态仅作用于对应图',await ids(page),expectedIds(w6.filter(b=>b.status==='failure')));
   const npuBefore=await ids(page,'npuChart');
   await page.locator('[data-filter="running"]').click();
   record('T11','E2E 状态不改变 NPU 图',await ids(page,'npuChart'),npuBefore);
   await page.locator('[data-npu-filter="failure"]').click();
   record('T12','NPU 独立状态筛选',await ids(page,'npuChart'),expectedIds(w6.filter(b=>b.npu_queue_seconds!=null&&b.status==='failure')));
   await page.locator('[data-filter="all"]').click();await page.locator('[data-npu-filter="all"]').click();
   const query=String((w6[0]||payload.batches[0]).pr);
   await page.locator(role('search')).fill(query);
   record('T13','列表搜索尊重当前时间窗',await page.locator(role('attention')+' .row').count(),w6.filter(b=>String(b.pr||'').includes(query)||(b.title||'').toLowerCase().includes(query)).length,{query});
   record('T14','列表搜索不改变图表',await ids(page),expectedIds(w6));
   await page.locator(role('search')).fill('__no_matching_pr__');
   record('T15','列表无匹配提示',await page.locator(role('attention')+' .row').count(),0);
   await page.locator(role('search')).fill(query);
   const requests=[];await page.route('**/api/export',async route=>{const body=route.request().postDataJSON();requests.push(body);await route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({name:'triton-batches-audit.csv',url:'/audit-download.csv'})});});
   await page.locator(role('exportBatches')).click();await page.locator(role('exportNotice')).filter({hasText:'已保存'}).waitFor();
   fs.writeFileSync(OUT+'/evidence/triton-export.csv',requests[0].csv,'utf8');
   record('T16','Triton CSV 按分支/时间/列表搜索导出',requests[0].csv.trim().split(/\r?\n/).length-1,w6.filter(b=>String(b.pr||'').includes(query)||(b.title||'').toLowerCase().includes(query)).length,{kind:'real',postIntercepted:true,csv:'evidence/triton-export.csv'});
   if(!await page.locator(role('branchFilter')).evaluate(n=>n.open))await page.locator(role('branchFilter')+' summary').click();
   await page.locator(role('branchOptions')+' input').first().check();
   await page.locator('[data-filter="failure"]').click();
   const before=await getState(page);
   await page.locator('[data-nav="ubs-overview"]').click();await page.locator('#ubs-view').waitFor({state:'visible'});
   await page.locator('[data-nav="triton"]').click();await page.locator(role('chart')).waitFor({state:'visible'});
   record('T17','跨域返回保留 Triton 会话状态',await getState(page),before);
   await shot(page,'triton-return-state-reset');
   await ctx.close();
  });
  await guarded('triton-tooltip-drag-keyboard',async()=>{
   const {ctx,page}=await mount(browser);
   const mark=page.locator(role('chart')+' .mark-hit').first();await mark.hover();
   record('T18','散点悬浮卡片显示',await page.locator(role('tip')).isVisible(),true);
   await mark.click();await page.mouse.move(30,30);
   record('T19','卡片点击固定',await page.locator(role('tip')).isVisible(),true);
   record('T20','卡片可追溯原始链接',await page.locator(role('tip')+' a[href^="https://"]').count()>0,true);
   await shot(page,'triton-tooltip-pinned');
   await page.locator('h1').click();record('T21','点击外部关闭卡片',await page.locator(role('tip')).isVisible(),false);
   await page.locator('[data-hours="12"]').click();
   const nav=page.locator(role('navigator'));await nav.scrollIntoViewIfNeeded();
   const drag=async(sel,delta)=>{const b=await page.locator(sel).boundingBox();await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2+delta,b.y+b.height/2,{steps:8});await page.mouse.up();};
   const first=await text(page,'selectedRange');
   await drag(role('navigator')+' [data-drag="window"]',-120);
   record('T22','拖动时间窗口改变时间范围',(await text(page,'selectedRange'))!==first,true);
   const beforeStart=await text(page,'selectedRange');await drag(role('navigator')+' [data-drag="start"]',30);
   record('T23','拖动左边界改变范围',(await text(page,'selectedRange'))!==beforeStart,true);
   const beforeEnd=await text(page,'selectedRange');await drag(role('navigator')+' [data-drag="end"]',-30);
   record('T24','拖动右边界改变范围',(await text(page,'selectedRange'))!==beforeEnd,true);
   const navBox=await nav.boundingBox(),beforeJump=await text(page,'selectedRange');await page.mouse.click(navBox.x+20,navBox.y+20);
   record('T25','点击导航空白跳转窗口',(await text(page,'selectedRange'))!==beforeJump,true);
   const values=await nav.evaluate(n=>({tabindex:n.getAttribute('tabindex'),min:n.getAttribute('aria-valuemin'),max:n.getAttribute('aria-valuemax'),now:n.getAttribute('aria-valuenow')}));
   record('T26','时间滑块具备键盘与 slider 值',values.tabindex!==null&&values.min!==null&&values.max!==null&&values.now!==null,true,{observedAttributes:values});
   const main=page.locator(role('attention')+' .row-main').first();const tab=await main.getAttribute('tabindex');
   record('T27','关注批次展开入口可键盘聚焦',await main.evaluate(n=>n.matches('button,a,input,[tabindex]')),true,{tabindex:tab});
   await main.click();record('T28','关注批次点击展开',await main.evaluate(n=>n.parentElement.classList.contains('open')),true);
   await ctx.close();
  });
  await guarded('pages-export',async()=>{
   const ctx=await browser.newContext({acceptDownloads:true,viewport:{width:1440,height:1000}});const page=await ctx.newPage();
   await page.route('https://audit-pages.invalid/**',async route=>{const p=new URL(route.request().url()).pathname;const target=ROOT+'/web'+(p==='/'?'/index.html':p);if(!fs.existsSync(target)){await route.fulfill({status:404,body:'missing'});return;}await route.fulfill({status:200,contentType:target.endsWith('.json')?'application/json':target.endsWith('.js')?'text/javascript':target.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(target)});});
   await page.goto('https://audit-pages.invalid/#triton',{waitUntil:'networkidle'});await page.locator(role('chart')).waitFor();
   const downloadPromise=page.waitForEvent('download');await page.locator(role('exportBatches')).click();const dl=await downloadPromise;await dl.saveAs(OUT+'/evidence/triton-pages-export.csv');
   record('T29','Pages 使用浏览器下载 CSV',dl.suggestedFilename(),'triton-batches.csv',{csv:'evidence/triton-pages-export.csv',origin:'offline route mock of Pages',productionNetworkWrites:false});
   await ctx.close();
  });
  await guarded('failure-isolation',async()=>{
   for(const scenario of ['ubs-index-404','single-repo-404','triton-404','triton-bad-json','triton-empty']){
    const ctx=await browser.newContext();const page=await ctx.newPage();
    const failed=scenario.startsWith('ubs-index')?'**/data/repositories.json':scenario==='single-repo-404'?'**/data/repos/ubs-engine.json':'**/data/triton.json';
    await page.route(failed,async route=>{if(scenario==='triton-empty'){await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...payload,batches:[]})});}else if(scenario==='triton-bad-json'){await route.fulfill({status:200,contentType:'application/json',body:'{broken'});}else await route.fulfill({status:404,body:'missing'});});
    await page.goto(BASE+'#triton',{waitUntil:'networkidle'});
    const tritonVisible=await page.locator('#triton-view').isVisible();
    record('F01-'+scenario,'故障隔离 '+scenario,tritonVisible,true,{kind:'fault-injection'});
    if(scenario.startsWith('triton')){record('F02-'+scenario,'Triton 异常提供明确空态',await page.locator('#triton-view').textContent().then(t=>/暂无|失败|数据/.test(t)),true);await page.locator('[data-nav="ubs-overview"]').click();await page.locator('#ubs-view').waitFor({state:'visible'});record('F03-'+scenario,'Triton 异常不影响 UBS',await page.locator('#repositoryRows tr').count(),9);}
    if(scenario==='ubs-index-404'){await shot(page,'failure-ubs-index-blocks-triton');}
    await ctx.close();
   }
  });
  await guarded('reload-race',async()=>{
   const {ctx,page}=await mount(browser);let calls=0;const responded=[];
   await page.route('**/data/triton.json',async route=>{const n=++calls;const data={...payload,collected_at:n===1?'2026-10-08T00:00:00Z':'2026-10-09T00:00:00Z'};if(n===1)await new Promise(r=>setTimeout(r,450));await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});responded.push(n);});
   await page.locator('#reload').evaluate(n=>{n.click();n.click();});await page.waitForFunction(()=>window.tritonPayload?.collected_at==='2026-10-09T00:00:00Z');await page.waitForResponse(r=>r.url().endsWith('/data/triton.json')).catch(()=>{});
   await page.waitForFunction(()=>window.tritonPayload?.collected_at==='2026-10-08T00:00:00Z',{},{timeout:1500}).catch(()=>{});
   record('F04','连续刷新不能让旧响应覆盖新响应',await page.evaluate(()=>window.tritonPayload.collected_at),'2026-10-09T00:00:00Z',{kind:'fault-injection',responseOrder:responded});
   await shot(page,'reload-older-response-overwrites');await ctx.close();
  });
  await guarded('responsive-visual',async()=>{
   for(const [device,vp] of [['desktop',{width:1440,height:1000}],['tablet',{width:1024,height:768}],['mobile',{width:390,height:844}]]){
    const {ctx,page}=await mount(browser,'ubs',{viewport:vp,isMobile:device==='mobile',hasTouch:device==='mobile'});
    for(const hash of ['ubs','ubs/repo/ubs-engine','ubs/repo/ubs-engine/quality','method','triton']){
     await page.goto(BASE+'#'+hash,{waitUntil:'networkidle'});await page.locator(hash==='triton'?role('chart'):hash==='method'?'#method-view':hash.endsWith('quality')?'#quality':'#'+(hash==='ubs'?'ubs-view':'ubs-repo-view')).waitFor({state:'visible'});
     const name='visual-'+device+'-'+hash.replaceAll('/','-');const screenshot=await shot(page,name);
     const layout=await page.evaluate(()=>({viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,mainWidth:document.querySelector('main').getBoundingClientRect().width,nav:Array.from(document.querySelectorAll('.side-nav nav a')).map(n=>({text:n.textContent.trim(),title:n.getAttribute('title'),aria:n.getAttribute('aria-label'),width:n.getBoundingClientRect().width})),fontSize:getComputedStyle(document.querySelector('.side-nav nav a')).fontSize}));
     record('V-'+device+'-'+hash,'页面无整体横向溢出 '+device+' '+hash,layout.documentWidth<=vp.width+1,true,{screenshot,layout});
     if(device==='mobile'&&hash==='triton'){
      record('V-mobile-nav-label','手机导航仍可识别文字或替代标签',layout.fontSize!=='0px'||layout.nav.every(n=>n.title||n.aria),true,{layout,screenshot});
      const mark=page.locator(role('chart')+' .mark-hit').first();await mark.tap();record('V-mobile-tip','触屏散点显示详情',await page.locator(role('tip')).isVisible(),true);await shot(page,'visual-mobile-triton-tooltip');
     }
    }
    await ctx.close();
   }
  });
  await guarded('edge-smoke',async()=>{
   const edge=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
   try{const {ctx,page}=await mount(edge);record('E01','Edge 可挂载 Triton 两图',await page.locator(role('chart')+','+role('npuChart')).count(),2);await page.locator('[data-hours="6"]').click();record('E02','Edge 时间窗图表',await ids(page),expectedIds(select(payload.batches,6)));await page.locator('[data-nav="ubs-overview"]').click();await page.locator('#ubs-view').waitFor({state:'visible'});record('E03','Edge 跨域导航',await page.locator('#repositoryRows tr').count(),9);await ctx.close();}finally{await edge.close();}
  });
 } finally {
  await browser.close();
  const result={executed_at:new Date().toISOString(),artifact_sha256:crypto.createHash('sha256').update(fs.readFileSync(ROOT+'/web/data/triton.json')).digest('hex'),checks,screenshots,consoleErrors,counts:Object.fromEntries(['passed','failed','unverified'].map(s=>[s,checks.filter(c=>c.state===s).length]))};
  fs.writeFileSync(OUT+'/evidence/'+(process.env.AUDIT_RESULT||'triton-browser.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({summary:result.counts,consoleErrors}));
 }
})();
