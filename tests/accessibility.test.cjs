const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const css = fs.readFileSync(path.join(__dirname, '..', 'web', 'style.css'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const wbv = fs.readFileSync(path.join(__dirname, '..', 'web', 'workbench-view.js'), 'utf8');
const init = fs.readFileSync(path.join(__dirname, '..', 'web', 'shell-init.js'), 'utf8');
const tritonView = fs.readFileSync(path.join(__dirname, '..', 'web', 'triton-view.js'), 'utf8');

test('P-014: the new workbench selector and concern table expose accessible names', () => {
  assert.match(wbv, /<select id="projectSelector" aria-label="项目选择">/);
  assert.match(wbv, /<th scope="col">项目<\/th>/);
  assert.match(wbv, /<th scope="col">仓库<\/th>/);
});

test('P-014: workbench empty/error states announce themselves, not colour alone', () => {
  assert.match(wbv, /role="status">当前没有需要关注的记录/);
  assert.match(wbv, /role="status">没有启用的项目/);
  assert.match(init, /role="status">工作台目录读取失败/);
});

test('P-014: focus visibility and reduced motion remain preserved', () => {
  assert.match(css, /:focus-visible\{outline:2px solid var\(--accent\)/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)/);
});

test('P-014: keyboard paths are preserved (navigator sliders, Escape close, row toggle)', () => {
  assert.match(tritonView, /role="slider" tabindex="0" aria-label="时间范围整体窗口"/);
  assert.match(tritonView, /aria-label="时间范围\$\{side === 'start' \? '起点' : '终点'\}"/);
  assert.match(tritonView, /if \(e\.key === 'Escape'\) \{\s*e\.preventDefault\(\); hideTip\(\)/);
  assert.match(tritonView, /aria-expanded="false" aria-controls=/);
});

test('P-014: trend chart and list search keep accessible names', () => {
  assert.match(html, /<input id="query"[^>]*aria-label="搜索 PR">/);
  assert.match(html, /aria-label="数据筛选"/);
});