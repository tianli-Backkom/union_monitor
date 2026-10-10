const { test } = require('node:test');
const assert = require('node:assert/strict');

const M = require('../web/core.js');

test('P-010: exportMetadata carries the versioned, self-describing fields', () => {
  const md = M.exportMetadata({
    entity: 'PR 全部批次', scope: 'ubs-engine PR 代表样本', list_condition: 'q=248',
    count: 5, unit: '分钟', duration_unit: '分钟', profile_version: 'ubs-pr-representative-v1',
    snapshot_id: 'rel-20261009', collected_at: '2026-10-09T23:30:00Z', time_basis: 'pr_created_at',
  });
  assert.equal(md.format, 'ubs-core-export');
  assert.equal(md.format_version, 1);
  assert.equal(md.entity, 'PR 全部批次');
  assert.equal(md.count, 5);
  assert.equal(md.profile_version, 'ubs-pr-representative-v1');
  assert.equal(md.snapshot_id, 'rel-20261009');
  assert.equal(md.time_basis, 'pr_created_at');
});

test('P-010: missing metadata defaults keep an honest null/safe count', () => {
  const md = M.exportMetadata();
  assert.equal(md.format_version, 1);
  assert.equal(md.count, null);
  assert.equal(md.duration_unit, '分钟');
});

test('P-010: exportSummary spells out entity/scope/conditions/count/versions', () => {
  const summary = M.exportSummary({
    entity: 'PR 全部批次', scope: 'ubs-engine PR 代表样本', list_condition: 'q=248',
    count: 5, unit: '分钟', snapshot_id: 'rel-20261009', profile_version: 'ubs-pr-representative-v1',
  });
  assert.match(summary, /实体：PR 全部批次/);
  assert.match(summary, /分析范围：ubs-engine PR 代表样本/);
  assert.match(summary, /列表条件：q=248/);
  assert.match(summary, /条数：5/);
  assert.match(summary, /单位：分钟/);
  assert.match(summary, /数据版本：rel-20261009/);
  assert.match(summary, /口径版本：ubs-pr-representative-v1/);
});

test('P-010: a zero-count export is legal and says 0, not a fake empty success', () => {
  const md = M.exportMetadata({ entity: 'PR 列表', count: 0 });
  assert.equal(md.count, 0);
  assert.match(M.exportSummary({ entity: 'PR 列表', count: 0 }), /条数：0/);
});

test('P-010: the CSV body stays free of comment rows at the top', () => {
  const content = M.csv([['仓库', 'PR'], ['openeuler/ubs-engine', 248]]);
  assert.equal(content.charCodeAt(0), 0xfeff); // BOM, then the header row
  assert.match(content, /^﻿"仓库","PR"/);
  assert.doesNotMatch(content.split('\r\n')[0], /^#/);
});

test('P-010: saveCsv accepts optional metadata and returns it alongside the file', async () => {
  const env = {
    location: { hostname: 'example.com' },
    Blob: class { constructor(parts, opts) { this.parts = parts; this.opts = opts; } },
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} },
    document: { createElement: () => ({ href: '', download: '', click() {} }) },
  };
  const result = await M.saveCsv([['仓库']], 'a.csv', env, { entity: 'PR 列表', count: 2 });
  assert.equal(result.mode, 'download');
  assert.equal(result.metadata.format, 'ubs-core-export');
  assert.equal(result.metadata.count, 2);
});