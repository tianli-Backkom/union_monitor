const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const css=fs.readFileSync(path.join(__dirname,'..','web','style.css'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'..','web','index.html'),'utf8');
const app=fs.readFileSync(path.join(__dirname,'..','web','app.js'),'utf8');

/* ---- REQ-030: mobile topbar keeps actions fully visible (static layout contract) ---- */

test('REQ-030 AC01: topbar grows instead of clipping — min-height floor, wrap allowed, no fixed 64px height',()=>{
  const rule=css.match(/\.topbar\{[^}]*\}/)[0];
  assert.ok(rule,'.topbar rule exists');
  assert.match(rule,/min-height:64px/,'keeps the 64px floor');
  assert.doesNotMatch(rule,/(?<!-)height:64px/,'a fixed 64px height clipped the reload button out of the bar at 390×844');
  assert.match(rule,/flex-wrap:wrap/,'breadcrumb and actions wrap into rows instead of squeezing');
  assert.match(rule,/row-gap:/,'wrapped rows keep spacing');
});

test('REQ-030 AC01: text buttons stay single-line and never collapse into a per-character column',()=>{
  const rule=css.match(/\.text-button\{[^}]*\}/)[0];
  assert.match(rule,/white-space:nowrap/);
  assert.match(rule,/flex-shrink:0/);
});

test('REQ-030 AC02: topbar padding keeps vertical breathing room at every breakpoint',()=>{
  const base=css.match(/\.topbar\{[^}]*\}/)[0];
  const media=[...css.matchAll(/\.topbar\{padding:[^}]*\}/g)].map(m=>m[0]);
  assert.equal(media.length,2,'the 1150px and 800px overrides');
  for(const rule of [base,...media]){
    const p=rule.match(/padding:([^;}]+)/)[1];
    assert.ok(!p.trim().startsWith('0'),'vertical padding must not be zeroed: '+p);
  }
});

test('REQ-030 AC02: repository controls wrap instead of overflowing once text buttons stop shrinking',()=>{
  const rule=css.match(/\.repository-controls\{[^}]*\}/)[0];
  assert.ok(rule,'.repository-controls rule exists');
  assert.match(rule,/flex-wrap:wrap/);
});

test('REQ-030 AC03: reload keeps a visible name, an accessible hint, and the same wiring',()=>{
  const tag=html.match(/<button id="reload"[^>]*>/)[0];
  assert.match(tag,/title="重新加载快照"/,'accessible hint');
  const full=html.match(/<button id="reload"[\s\S]*?<\/button>/)[0];
  assert.match(full,/重新加载快照/,'recognizable visible name, not icon-only');
  assert.match(app,/\$\('reload'\)\.onclick=load/,'click/touch still routes to the same load()');
});
