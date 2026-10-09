const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const assert=require('node:assert');
const {test}=require('node:test');
const app=readFileSync(join(__dirname,'..','web','app.js'),'utf8');

test('REQ-036 AC01/AC02: navigate() 对直接目标导航推进历史，仅规范化替换当前记录',()=>{
  assert.match(app,/if\(hash===canonical\)history\.pushState\(null,'',canonical\);else history\.replaceState\(null,'',canonical\)/,'selector/repo/back-to-overview navigation pushes a history entry; legacy/invalid normalization only replaces');
});

test('REQ-036 AC02: hashchange 保持 navigate 单一路径，历史写入有守卫不产生重复条目',()=>{
  assert.match(app,/window\.addEventListener\('hashchange',\(\)=>navigate\(location\.hash\)\)/,'hashchange routes through the same navigate path');
  assert.match(app,/if\(canonical!==location\.hash\)\{/,'the history write is guarded so hashchange re-entry never duplicates entries');
});
