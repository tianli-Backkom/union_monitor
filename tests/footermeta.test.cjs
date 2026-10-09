const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const assert=require('node:assert');
const {test}=require('node:test');
const app=readFileSync(join(__dirname,'..','web','app.js'),'utf8');
const view=readFileSync(join(__dirname,'..','web','triton-view.js'),'utf8');

test('REQ-035 AC01: 口径页清空页脚，UBS 跨仓未读取时不遗留旧域数值',()=>{
  assert.match(app,/domain==='method'\)\$\('footerMeta'\)\.textContent=''/,'method clears the footer');
  assert.match(app,/cross&&!repositoryIndex\)\$\('footerMeta'\)\.textContent=''/,'cross view without index clears the footer');
});

test('REQ-035 AC02/AC03: Triton 域先置快照范围默认并标注，失败有明确提示而非旧域数值',()=>{
  assert.match(app,/快照范围 · 采集于 \$\{date\(Date\.parse\(p\.collected_at\)\)\}/,'snapshot-scope default derived from the Triton payload');
  assert.match(app,/TRITON 数据读取失败'/,'failure note instead of previous-domain numbers');
});

test('REQ-035 AC02: 视图页脚与摘要条共用 pageSet（G）并标注当前筛选范围',()=>{
  assert.match(view,/const footerText = \(\) => \{[\s\S]*?currentSummary\(\);[\s\S]*?当前筛选范围 · 采集于 \$\{fmtDate\(D\.collected_at\)\}`/,'footerText derives from the same summary set');
  assert.match(view,/if \(fm\) fm\.textContent = footerText\(\);/,'updateSummary syncs the footer');
});

test('REQ-035 AC03: sameSessionMount 早退路径重新同步页脚，reload 双导航后不残留快照默认',()=>{
  assert.match(view,/if \(fm && active\) fm\.textContent = active\.footerText\(\);/,'early-return path re-syncs from the live view state');
});
