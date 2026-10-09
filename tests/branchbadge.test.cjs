const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const { branchBadgeText } = require('../web/triton-core.js');
const html=fs.readFileSync(path.join(__dirname,'..','web','index.html'),'utf8');
const app=fs.readFileSync(path.join(__dirname,'..','web','app.js'),'utf8');
const view=fs.readFileSync(path.join(__dirname,'..','web','triton-view.js'),'utf8');

/* ---- REQ-033: topbar branch badge follows the active domain ---- */

test('REQ-033 AC01: branchBadgeText maps the selection to badge text (all/single/multi)',()=>{
  assert.deepEqual(branchBadgeText([]),{text:'全部目标分支'});
  assert.deepEqual(branchBadgeText(['main']),{text:'main'});
  assert.deepEqual(branchBadgeText(['main-dev','main']),{text:'已选 2 个分支',title:'main、main-dev'},'multi shows a count and lists branches in a stable sorted title');
  assert.equal(branchBadgeText(['release/3.2.2','main','main-dev']).title,'main、main-dev、release/3.2.2');
});

test('REQ-033 AC02: the badge is script-managed with a stable name element',()=>{
  const tag=html.match(/<span class="branch"[^>]*>/)[0];
  assert.match(tag,/id="branchBadge"/);
  assert.ok(html.includes('id="branchName"'),'name text lives in its own element so scripts never wipe the icon');
});

test('REQ-033 AC02/AC03: applyRoute hides the badge on the method page and derives UBS text from snapshot meta.branch',()=>{
  assert.match(app,/\$\('branchBadge'\)\.hidden=domain==='method'/);
  assert.match(app,/meta\.branch/,'UBS badge text derives from snapshot meta.branch');
  assert.match(app,/'全部目标分支'/,'Triton resets to the all-branches default before the view overwrites it');
});

test('REQ-033 AC01: renderBranchOptions syncs the topbar badge on every selection change',()=>{
  assert.match(view,/function syncBranchBadge\(branches\)/,'module-level badge sync helper');
  assert.match(view,/core\.branchBadgeText\(branches\)/,'the helper maps the selection through the pure function');
  assert.match(view,/syncBranchBadge\(\[\.\.\.selectedBranches\]\)/,'selection changes update the badge');
});

test('REQ-033 AC03: the sameSessionMount early-return path re-syncs the badge after a reload reset it',()=>{
  assert.match(view,/if \(core\.sameSessionMount\(mounted, payload, container\)\) \{\s*syncBranchBadge\(active \? active\.state\(\)\.branches : \[\]\);/,'same-data reloads skip the remount but must not leave the reset default in place');
});
