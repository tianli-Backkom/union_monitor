const { test, expect } = require('@playwright/test');

async function readDownload(download) {
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

// UDR-017: unified detail + source evidence path. List / chart (exception) /
// attention (failed-wait) all enter the same #detail modal; a PR defaults to
// its representative batch, a direct batch entry expands that batch, and a
// no-representative PR shows the reason plus the most-recent batch without
// fabricating a representative. The detail binds identity, version and an
// evidence boundary, and closing returns to the source list.

function makeBatch(number, e2e_ms, event_id, opts = {}) {
  const result = opts.result || 'SUCCESS';
  const url = `https://ci.openeuler.openatom.cn/job/ubs-engine/key/${number}/`;
  return {
    url, number, request_ms: 1000, scheduled_ms: 900, complete: true,
    end_ms: 1000 + e2e_ms, e2e_ms, jenkins_ms: e2e_ms,
    status: opts.status || (result === 'SUCCESS' ? 'success' : 'failure'),
    cancelled: !!opts.cancelled, eligible: opts.eligible !== false,
    event_id, sha: opts.sha || 'sha1', event_type: opts.event_type || 'create',
    association: 'gitcode 关联信息', webhook_ms: 950,
    trigger: { kind: 'trigger', number, url, queue_ms: 50, duration_ms: e2e_ms, total_ms: e2e_ms + 50, result, start_ms: 1000, end_ms: 1000 + e2e_ms, scheduled_ms: 900 },
    children: opts.children || [], issues: opts.issues || [],
  };
}

function fixture() {
  const pr100 = {
    number: 100, state: 'merged', created_ms: 500, merged_ms: 4000, closed_ms: null,
    title: 'PR 100 three batches', author: 'dev', submission_count: 3, head_sha: 'aaa',
    events: [
      { id: 'e1', kind: 'create', time_ms: 400, sha: 'a1' },
      { id: 'e2', kind: 'push', time_ms: 600, sha: 'a2' },
      { id: 'e3', kind: 'push', time_ms: 800, sha: 'a3' },
    ],
    issues: [],
    batches: [
      makeBatch(1, 3000, 'e1'),
      makeBatch(2, 5000, 'e2', { children: [
        { kind: 'x86', number: 12, url: 'https://ci.openeuler.openatom.cn/job/ubs-engine/x86/12/', queue_ms: 500, duration_ms: 2000, total_ms: 2500, result: 'SUCCESS' },
      ] }),
      makeBatch(3, 4000, 'e3', { result: 'FAILURE', status: 'failure' }),
    ],
  };
  const pr200 = {
    number: 200, state: 'open', created_ms: 700, merged_ms: null, closed_ms: null,
    title: 'PR 200 no representative', author: 'dev', submission_count: 1, head_sha: 'bbb',
    events: [], issues: ['创建请求与 PR 关联未知', '2 个批次非有效样本'],
    batches: [
      makeBatch(4, 6000, 'e9', { eligible: false }),
      makeBatch(5, 9000, 'e9', { eligible: false }),
    ],
  };
  return {
    repositories: {
      schema_version: 3, start_ms: 1000, end_ms: 9000,
      generated_at: '2026-10-12T00:00:00Z',
      repositories: [
        { name: 'ubs-engine', repository: 'openeuler/ubs-engine', snapshot: 'repos/ubs-engine.json', status: 'success' },
      ],
    },
    snapshot: {
      meta: { repository: 'openeuler/ubs-engine', start_ms: 1000, end_ms: 9000, collected_at: '2026-10-12T00:00:00Z', branch: 'master', errors: [] },
      prs: [pr100, pr200],
    },
  };
}

async function serveUbs(page, data) {
  await page.route('**/data/repositories.json*', route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data.repositories) }));
  await page.route('**/data/repos/ubs-engine.json*', route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data.snapshot) }));
}

test('three entries converge on one detail; representative default vs selected batch', async ({ page }) => {
  await serveUbs(page, fixture());
  const dialog = page.locator('#detail');

  // List entry (repo view) → default representative (batch 2) expanded.
  await page.goto('./#ubs/repo/ubs-engine');
  await page.locator('#entity').selectOption('prs');
  await expect(page.locator('#prRows tr[data-pr="100"]')).toBeVisible();
  await page.locator('#prRows tr[data-pr="100"]').click();
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('[data-role="evidence"]')).toContainText('数据版本');
  await expect(dialog.locator('[data-role="evidence"]')).toContainText('证据覆盖边界');
  await expect(dialog.locator('details[data-batch-url$="/key/2/"]')).toHaveAttribute('data-expand-reason', 'representative');
  await expect(dialog.locator('details[data-batch-url$="/key/2/"]')).toHaveAttribute('open', '');
  await expect(dialog.locator('details[data-batch-url$="/key/1/"]')).not.toHaveAttribute('open', '');
  await expect(dialog.locator('details[data-batch-url$="/key/3/"]')).not.toHaveAttribute('open', '');
  await page.locator('#closeDetail').click();
  await expect(dialog).toBeHidden();

  // Attention (failed-wait) entry → the selected batch (3) expands.
  await page.goto('./#ubs');
  await expect(page.locator('#failedWaitRows [data-pr="100"]')).toBeVisible();
  await page.locator('#failedWaitRows [data-pr="100"]').click();
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('details[data-batch-url$="/key/3/"]')).toHaveAttribute('data-expand-reason', 'entry');
  await expect(dialog.locator('details[data-batch-url$="/key/3/"]')).toHaveAttribute('open', '');
  await page.locator('#closeDetail').click();
  await expect(dialog).toBeHidden();

  // Chart (exception) entry → same modal, representative default again.
  await page.goto('./#ubs');
  await expect(page.locator('#exceptionRows [data-exception="100"]')).toBeVisible();
  await page.locator('#exceptionRows [data-exception="100"]').click();
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('details[data-batch-url$="/key/2/"]')).toHaveAttribute('data-expand-reason', 'representative');
  await page.locator('#closeDetail').click();
  await expect(dialog).toBeHidden();
});

test('no-representative PR shows the reason and the most-recent batch, never a fabricated representative', async ({ page }) => {
  await serveUbs(page, fixture());
  await page.goto('./#ubs/repo/ubs-engine');
  await page.locator('#entity').selectOption('prs');
  await expect(page.locator('#prRows tr[data-pr="200"]')).toBeVisible();
  await page.locator('#prRows tr[data-pr="200"]').click();
  const dialog = page.locator('#detail');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('[data-role="no-representative"]')).toContainText('该 PR 无代表批次');
  await expect(dialog.locator('[data-role="no-representative"]')).toContainText('Trigger #5');
  await expect(dialog.locator('details[data-batch-url$="/key/5/"]')).toHaveAttribute('data-expand-reason', 'no-representative');
  await expect(dialog.locator('details[data-batch-url$="/key/5/"]')).toHaveAttribute('open', '');
  // No batch is marked as the representative.
  await expect(dialog.locator('details.representative')).toHaveCount(0);
});

test('unknown-association batches stay locatable and closing returns to the list', async ({ page }) => {
  await serveUbs(page, fixture());
  await page.goto('./#ubs/repo/ubs-engine');
  await page.locator('#entity').selectOption('prs');
  await expect(page.locator('#prRows tr[data-pr="200"]')).toBeVisible();
  await page.locator('#prRows tr[data-pr="200"]').click();
  const dialog = page.locator('#detail');
  await expect(dialog).toBeVisible();
  // The two unmatched batches are both present under 关联未知/失配.
  await expect(dialog.locator('.event-heading', { hasText: '关联未知' })).toBeVisible();
  await expect(dialog.locator('details[data-batch-url$="/key/4/"]')).toBeVisible();
  await expect(dialog.locator('details[data-batch-url$="/key/5/"]')).toBeVisible();
  // Source links render as external anchors and never collapse the expanded row.
  await expect(dialog.locator('details[data-batch-url$="/key/5/"] a[target="_blank"]').first()).toBeVisible();
  await page.locator('#closeDetail').click();
  await expect(dialog).toBeHidden();
  await expect(page.locator('#prRows')).toBeVisible();
});

test('selected-batch task export binds the selected batch tasks, never the whole PR', async ({ page }) => {
  await serveUbs(page, fixture());
  await page.goto('./#ubs/repo/ubs-engine');
  await page.locator('#entity').selectOption('prs');
  await expect(page.locator('#prRows tr[data-pr="100"]')).toBeVisible();
  await page.locator('#prRows tr[data-pr="100"]').click();
  const dialog = page.locator('#detail');
  await expect(dialog).toBeVisible();
  // Default selection is the representative (batch 2) with two tasks.
  await expect(dialog.locator('details[data-batch-url$="/key/2/"]')).toHaveAttribute('open', '');
  const downloadEvent = page.waitForEvent('download');
  await page.locator('#exportBatchTasks').click();
  const csv = await readDownload(await downloadEvent);
  const lines = csv.replace(/^\uFEFF/, '').trim().split(/\r?\n/);
  expect(lines[0]).toMatch(/^"仓库","PR","批次","任务类型"/);
  expect(lines.length - 1).toBe(2);
  await expect(dialog.locator('.export-notice')).toContainText('实体：选中批次任务');
  await expect(dialog.locator('.export-notice')).toContainText('条数：2');
});

test('deduplicated-concern export collapses duplicate reasons by batch identity', async ({ page }) => {
  await serveUbs(page, fixture());
  await page.goto('./#ubs/repo/ubs-engine/quality');
  await expect(page.locator('#qualityContent .quality-row')).toHaveCount(2);
  const downloadEvent = page.waitForEvent('download');
  await page.locator('#exportQuality').click();
  const csv = await readDownload(await downloadEvent);
  const lines = csv.replace(/^\uFEFF/, '').trim().split(/\r?\n/);
  expect(lines[0]).toMatch(/^"仓库","PR","批次","原因"/);
  expect(lines.length - 1).toBe(1);
  expect(lines[1]).toContain('创建请求与 PR 关联未知');
  expect(lines[1]).toContain('2 个批次非有效样本');
  await expect(page.locator('.export-notice')).toContainText('实体：去重关注');
  await expect(page.locator('.export-notice')).toContainText('条数：1');
});