const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const assert=require('node:assert');
const {test}=require('node:test');
const html=readFileSync(join(__dirname,'..','web','index.html'),'utf8');
const app=readFileSync(join(__dirname,'..','web','app.js'),'utf8');

test('REQ-034: 侧栏代码仓链接文本节点可独立更新',()=>{
  assert.match(html,/<a id="repositoryLink"[^>]*><span id="repositoryLinkText">查看代码仓<\/span>/,'link text wrapped in an updatable span');
});

test('REQ-034 AC01: Triton 域链接指向 triton-ascend GitHub 仓库',()=>{
  assert.match(app,/domain==='triton'\)\{repoLink\.hidden=false;repoLink\.href='https:\/\/github\.com\/triton-lang\/triton-ascend'/,'Triton links to the GitHub repo, never gitcode');
});

test('REQ-034: 口径页隐藏代码仓链接，不伪装单仓对象',()=>{
  assert.match(app,/domain==='method'\)repoLink\.hidden=true/,'method page hides the link');
});

test('REQ-034 AC03: 跨仓总览为组织目录参考链接，名称可区分单仓来源',()=>{
  assert.match(app,/cross\)\{repoLink\.hidden=false;repoLink\.href='https:\/\/gitcode\.com\/openeuler';repoLinkText\.textContent='openEuler 仓库组'/,'cross view links to the org directory with a distinct name');
  assert.match(app,/跨仓总览参考链接/,'tooltip states the reference nature');
});

test('REQ-034 AC02: 单仓链接使用当前仓库标识与提示',()=>{
  assert.match(app,/repoLink\.href='https:\/\/gitcode\.com\/openeuler\/'\+encodeURIComponent\(currentRepository\)/,'single-repo href follows currentRepository');
  assert.match(app,/repoLink\.title=currentRepository\+' · GitCode'/,'tooltip names the current repo');
});
