/* Browser fault and reload-order probes. Reads localhost and fixtures only; all exports intercepted. */
const fs=require('node:fs'),path=require('node:path');
const {chromium}=require('C:/Users/tianli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ROOT=path.resolve(__dirname,'../../..'),OUT=path.join(ROOT,'audit/2026-10-10/evidence/fault-adversarial.json'),SITE='http://127.0.0.1:8765';
const index=JSON.parse(fs.readFileSync(path.join(ROOT,'web/data/repositories.json'),'utf8'));
const triton=JSON.parse(fs.readFileSync(path.join(ROOT,'web/data/triton.json'),'utf8'));
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const report={generated_at:new Date().toISOString(),scope:'REQ010 explicit404/badJSON/empty; REQ011 failure/pending; reload-generation ordering',cases:[],exports:[],errors:[],network_write_policy:'All /api/export intercepted; no collection refresh or deployment'};
let browser;
async function snapshot(page){return page.evaluate(()=>({hash:location.hash,ubsStatus:typeof ubsStatus==='undefined'?null:ubsStatus,tritonStatus:typeof tritonStatus==='undefined'?null:tritonStatus,collected_at:window.tritonPayload?.collected_at||null,ubs_rows:document.querySelectorAll('#repositoryRows tr').length,ubs_visible:!document.querySelector('#ubs-view').hidden,triton_visible:!document.querySelector('#triton-view').hidden,triton_charts:document.querySelectorAll('#triton-view svg[data-role],#triton-view svg').length,triton_text:document.querySelector('#triton-view').textContent.slice(0,300),method_visible:!document.querySelector('#method-view').hidden,method_text:document.querySelector('#method-view').textContent,loading:document.querySelector('#loading').textContent,loading_visible:!document.querySelector('#loading').hidden}));}
async function setup(name,ubs,tritonMode,hash){
 const context=await browser.newContext();const page=await context.newPage();page.setDefaultTimeout(1500);page.on('pageerror',error=>report.errors.push({case:name,error:String(error)}));
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname==='/api/export'){report.exports.push({case:name,method:route.request().method(),body:route.request().postData()});return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({url:'/exports/audit-intercept.csv',name:'audit-intercept.csv'})});}
  if(url.pathname.endsWith('/data/repositories.json')){
   if(ubs==='pending')await wait(650);
   if(ubs==='404')return route.fulfill({status:404,body:'not found'});
   if(ubs==='badJSON')return route.fulfill({status:200,contentType:'application/json',body:'{invalid'});
  }
  if(url.pathname.endsWith('/data/triton.json')){
   if(tritonMode==='pending')await wait(650);
   if(tritonMode==='404')return route.fulfill({status:404,body:'not found'});
   if(tritonMode==='badJSON')return route.fulfill({status:200,contentType:'application/json',body:'{invalid'});
   if(tritonMode==='empty')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...triton,batches:[],summary:{prs:0,batches:0,valid:0,median:null,p90:null,approximate:0,incomplete:0,api_calls:0}})});
  }
  if(url.origin!==SITE)return route.abort();
  return route.continue();
 });
 await page.goto(SITE+'/'+hash,{waitUntil:'domcontentloaded',timeout:5000});return {context,page};
}
(async()=>{
 try{
  browser=await chromium.launch({channel:'chrome',headless:true});
  for(const bad of ['404','badJSON']){
   const name='UBS '+bad+' healthyTriton';const {context,page}=await setup(name,bad,'healthy','#triton');
   await page.waitForFunction(()=>tritonStatus==='ok'&&ubsStatus==='failed');await wait(100);
   const state=await snapshot(page);await page.locator('[data-role="exportBatches"]').click();
   report.cases.push({id:name,state,passed:state.triton_visible&&state.triton_charts>=2&&state.tritonStatus==='ok',export_intercepted:report.exports.some(x=>x.case===name)});
   await page.locator('a[href="#method"]').click();await page.waitForFunction(()=>!document.querySelector('#method-view').hidden);const method=await snapshot(page);report.cases.push({id:name+' method',state:method,passed:method.method_visible&&method.method_text.includes('openEuler UBS')&&method.method_text.includes('Triton-Ascend')});await context.close();
  }
  for(const bad of ['404','badJSON','empty']){
   const name='Triton '+bad+' healthyUBS';const {context,page}=await setup(name,'healthy',bad,'#ubs');
   await page.waitForFunction(()=>ubsStatus==='ok');const state=await snapshot(page);
   await page.locator('a[href="#ubs/repo/ubs-engine"]').first().click();await page.waitForFunction(()=>!document.querySelector('#ubs-repo-view').hidden);const repo=await page.evaluate(()=>({visible:!document.querySelector('#ubs-repo-view').hidden,rows:document.querySelectorAll('#prRows tr[data-pr]').length}));
   await page.locator('a[href="#triton"]').click();await page.waitForFunction(()=>!document.querySelector('#triton-view').hidden);const badState=await snapshot(page);
   report.cases.push({id:name,state,repository:repo,fault_state:badState,passed:state.ubs_visible&&state.ubs_rows===9&&repo.visible&&repo.rows>0&&(bad==='empty'?badState.tritonStatus==='ok':badState.tritonStatus==='failed')});await context.close();
  }
  for(const spec of [{id:'method bothFailed',ubs:'404',triton:'404'},{id:'method bothPending',ubs:'pending',triton:'pending'}]){
   const {context,page}=await setup(spec.id,spec.ubs,spec.triton,'#method');const immediate=await snapshot(page);await wait(850);const later=await snapshot(page);
   report.cases.push({id:spec.id,immediate,later,passed:immediate.method_visible&&later.method_visible&&immediate.method_text.includes('openEuler UBS')&&immediate.method_text.includes('Triton-Ascend')});
   if(spec.ubs==='404'){await page.locator('a[href="#ubs"]').first().click();await page.waitForFunction(()=>document.querySelector('#method-view').hidden);const back=await snapshot(page);report.cases.push({id:'method return preservesUBSFailure',state:back,passed:back.ubsStatus==='failed'&&back.loading_visible});}
   await context.close();
  }
  for(const firstFailure of [false,true]){
   const context=await browser.newContext();const page=await context.newPage();page.setDefaultTimeout(1500);let active=false,ordinal=0;const name=firstFailure?'reload lateFirstFailure':'reload lateFirstSuccess';const requests=[];
   page.on('pageerror',error=>report.errors.push({case:name,error:String(error)}));
   await page.route('**/*',async route=>{const url=new URL(route.request().url());if(url.pathname==='/api/export')return route.fulfill({status:201,contentType:'application/json',body:'{"url":"/exports/audit.csv","name":"audit.csv"}'});if(url.origin!==SITE)return route.abort();if(active&&url.pathname.endsWith('/data/triton.json')){const n=++ordinal;requests.push({ordinal:n,requested_at:Date.now()});if(n===1)await wait(450);if(n===1&&firstFailure)return route.fulfill({status:500,body:'late old failure'});return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...triton,collected_at:n===1?'2026-10-10T00:01:00Z':'2026-10-10T00:02:00Z'})});}return route.continue();});
   await page.goto(SITE+'/#triton',{waitUntil:'domcontentloaded',timeout:5000});await page.waitForFunction(()=>ubsStatus==='ok'&&tritonStatus==='ok');active=true;
   await page.locator('#reload').click();await wait(30);await page.locator('#reload').click();await wait(700);const state=await snapshot(page);
   report.cases.push({id:name,requests,state,passed:ordinal===2&&state.collected_at==='2026-10-10T00:02:00Z'&&state.tritonStatus==='ok'&&state.ubsStatus==='ok'&&!state.triton_text.includes('重新读取失败')});await context.close();
  }
 }catch(error){report.errors.push({phase:'runner',error:String(error),stack:error.stack});report.incomplete=true;}
 finally{if(browser)await browser.close();report.completed_at=new Date().toISOString();report.counts={passed:report.cases.filter(x=>x.passed).length,failed:report.cases.filter(x=>!x.passed).length,total:report.cases.length};fs.writeFileSync(OUT,JSON.stringify(report,null,2));console.log(JSON.stringify({output:OUT,counts:report.counts,errors:report.errors,incomplete:report.incomplete||false}));}
})();
