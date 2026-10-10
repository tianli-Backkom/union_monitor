#!/usr/bin/env node
/* A06 整改复验探针：按域提交 + 读取超时 + 代次保护（真实 Chromium + 合成悬挂响应）。

以 audit/2026-10-10 对抗审查 A06 的同一组输入复跑反例：拦截 data/triton.json
暂不返回，等待九个 UBS 仓库响应全部完成后，生产页面必须在当前 generation 内
按域提交 UBS 结果（ubsStatus='ok'、索引已提交、总览满行），不得被挂起的
Triton 请求跨域阻塞；随后 30 秒读取超时使 Triton 呈现明确失败提示而非无限
加载；反向拦截仓库索引时 Triton 两图仍可用且 UBS 按超时失败提示；第一代次
迟到的 Triton 响应不覆盖第二代次已提交的数据。

需要本地服务（python3 serve.py --port 8766）与缓存 Chromium；playwright-core
经 NODE_PATH 解析。全部拦截为进程内合成路由，不修改任何业务源码、测试、
冻结证据或真实快照；证据仅写入 audit/2026-10-10-remediation/。 */
'use strict';
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const {chromium}=require('playwright-core');
const ROOT=path.resolve(__dirname,'..','..','..');
const BASE=process.env.A06_BASE||'http://127.0.0.1:8766/';
const OUTDIR=path.join(ROOT,'audit','2026-10-10-remediation','evidence');
const SHOTS=path.join(ROOT,'audit','2026-10-10-remediation','screenshots');
const EXEC=process.env.A06_CHROME||['/home/tianli/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome','/home/tianli/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'].find(p=>fs.existsSync(p));
if(!EXEC)throw Error('未找到缓存的 Chromium，可通过 A06_CHROME 环境变量指定可执行文件');
const seed=JSON.parse(fs.readFileSync(path.join(ROOT,'web','data','triton.json'),'utf8'));
const index=JSON.parse(fs.readFileSync(path.join(ROOT,'web','data','repositories.json'),'utf8'));
const EXPECTED_ROWS=Array.isArray(index.repositories)?index.repositories.length:0;
const pageErrors=[],checks={},probes={};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function shot(page,name){await page.screenshot({path:path.join(SHOTS,'a06-'+name+'.png'),fullPage:false,animations:'disabled'});return 'audit/2026-10-10-remediation/screenshots/a06-'+name+'.png';}

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:EXEC});
 try{
  /* 场景 1/2：Triton 挂起时 UBS 按域提交，随后 Triton 超时给出失败提示。 */
  {
   const ctx=await browser.newContext({viewport:{width:1440,height:1000}});
   const page=await ctx.newPage();page.on('pageerror',e=>pageErrors.push('S12:'+e.message));
   let release;const hold=new Promise(r=>release=r);const responses=[];
   await page.route('**/data/triton.json',async r=>{await hold;await r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(seed)});});
   page.on('response',r=>{if(/\/data\/repos\/[^/]+\.json$/.test(r.url()))responses.push(r);});
   await page.goto(BASE+'#ubs',{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>document.querySelector('#repositoryRows .skel'),null,{timeout:5000});
   const until=Date.now()+5000;while(responses.length<EXPECTED_ROWS&&Date.now()<until)await sleep(50);
   await Promise.all(responses.map(r=>r.finished()));
   let hang;try{await page.waitForFunction(()=>ubsStatus==='ok',null,{timeout:3000});}catch(e){}
   hang=await page.evaluate(()=>({ubsStatus,repoAvailable:!!repositoryIndex,rows:document.querySelectorAll('#repositoryRows tr:has(a)').length}));
   probes.domain_hang={...hang,ubsResponsesCompleted:responses.length,expectedRows:EXPECTED_ROWS,screenshot:await shot(page,'ubs-committed-while-triton-hung')};
   checks.triton_hang_does_not_block_ubs=hang.ubsStatus==='ok'&&hang.repoAvailable===true&&hang.rows===EXPECTED_ROWS&&responses.length>=EXPECTED_ROWS;
   let timeout;try{await page.waitForFunction(()=>tritonStatus==='failed',null,{timeout:40000});}catch(e){}
   timeout=await page.evaluate(()=>({tritonStatus,tritonError}));
   await page.evaluate(()=>{location.hash='#triton';});
   await page.waitForSelector('#triton-view:not([hidden])',{timeout:5000}).catch(()=>{});
   const viewText=await page.evaluate(()=>document.querySelector('#triton-view').textContent);
   probes.triton_timeout={...timeout,viewText:viewText.slice(0,220),screenshot:await shot(page,'triton-timeout-prompt')};
   checks.triton_hang_ends_in_timeout_prompt=timeout.tritonStatus==='failed'&&/读取超时/.test(timeout.tritonError||'')&&/Triton 数据/.test(timeout.tritonError||'')&&viewText.includes('Triton 数据读取失败')&&viewText.includes('读取超时');
   release();await ctx.close();
  }
  /* 场景 3：仓库索引挂起时 Triton 可用，UBS 按超时失败提示。 */
  {
   const ctx=await browser.newContext({viewport:{width:1440,height:1000}});
   const page=await ctx.newPage();page.on('pageerror',e=>pageErrors.push('S3:'+e.message));
   let release;const hold=new Promise(r=>release=r);
   await page.route('**/data/repositories.json',async r=>{await hold;await r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({repositories:[]})});});
   await page.goto(BASE+'#triton',{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>tritonStatus==='ok',null,{timeout:10000});
   let tritonMounted=true;try{await page.waitForSelector('[data-role="chart"]',{timeout:5000});}catch(e){tritonMounted=false;}
   await page.evaluate(()=>{location.hash='#ubs';});
   let ubs;try{await page.waitForFunction(()=>ubsStatus==='failed',null,{timeout:40000});}catch(e){}
   ubs=await page.evaluate(()=>({ubsStatus,loading:document.querySelector('#loading').textContent}));
   probes.ubs_index_hang={tritonMounted,...ubs,screenshot:await shot(page,'ubs-index-timeout-banner')};
   checks.ubs_index_hang_leaves_triton_usable=tritonMounted===true;
   checks.ubs_index_timeout_prompt=ubs.ubsStatus==='failed'&&/仓库索引读取超时/.test(ubs.loading||'')&&/无法读取看板/.test(ubs.loading||'');
   release();await ctx.close();
  }
  /* 场景 4：第一代次 Triton 响应迟到，不覆盖第二代次已提交数据。 */
  {
   const ctx=await browser.newContext({viewport:{width:1440,height:1000}});
   const page=await ctx.newPage();page.on('pageerror',e=>pageErrors.push('S4:'+e.message));
   let tritonRequests=0,releaseFirst;const holdFirst=new Promise(r=>releaseFirst=r);
   await page.route('**/data/triton.json',async r=>{tritonRequests++;if(tritonRequests===1){await holdFirst;await r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...seed,batches:[]})});}else{await r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(seed)});}});
   await page.goto(BASE+'#ubs',{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>ubsStatus==='ok',null,{timeout:10000});
   await page.locator('#reload').click();
   await page.waitForFunction(()=>ubsStatus==='ok'&&tritonStatus==='ok',null,{timeout:15000});
   releaseFirst();await sleep(800);
   const after=await page.evaluate(()=>({tritonStatus,batches:(window.tritonPayload&&window.tritonPayload.batches||[]).length}));
   probes.generation_protection={tritonRequests,seedBatches:seed.batches.length,afterLateFirstResponse:after};
   checks.stale_generation_response_discarded=tritonRequests===2&&after.tritonStatus==='ok'&&after.batches===seed.batches.length;
   await ctx.close();
  }
 }finally{await browser.close();}
 const all=Object.values(checks).every(Boolean);
 const report={
  finding:'A06 · P1 · Triton请求挂起使已完成的UBS持续加载',requirements:['REQ-010'],
  generated_at:new Date().toISOString(),
  head:cp.execSync('git rev-parse HEAD',{cwd:ROOT,encoding:'utf8'}).trim(),
  base:BASE,chromium:EXEC,playwright:require('playwright-core/package.json').version,
  probes,checks,page_errors:pageErrors,all_counterexamples_defeated:all,
  notes:[
   'All network interception is in-process synthetic routing against the local read-only dashboard server; no production source, test, frozen audit evidence, or real snapshot was modified.',
   'Mirrors audit/2026-10-10/evidence/triton-adversarial.json check DOMAIN-HANG: open #ubs, hold data/triton.json, wait for all repository snapshot responses to finish, then require the current generation to commit the UBS domain.',
   'Extends the frozen input with the A06 remediation contract: per-domain commit, a 30-second read timeout with a distinct prompt in both directions, and generation protection against a late first-generation response.',
  ],
 };
 fs.mkdirSync(OUTDIR,{recursive:true});fs.mkdirSync(SHOTS,{recursive:true});
 fs.writeFileSync(path.join(OUTDIR,'a06-domain-hang.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({evidence:'audit/2026-10-10-remediation/evidence/a06-domain-hang.json',checks,page_errors:pageErrors.length,all_counterexamples_defeated:all},null,2));
 process.exitCode=all?0:1;
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
