const { test, expect } = require('@playwright/test');

// UDR-019: versioned public export. Each scope declares its entity, analysis
// scope, count and unit, and binds the release/snapshot identity. The CSV body
// stays free of comment rows (metadata travels in the on-screen summary, never
// in the file), and pagination never truncates the exported set.

async function readDownload(download) {
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

test('L record export binds the full filtered set and versioned metadata, not page-truncated', async ({ page }) => {
  await page.goto('./#ubs/repo/ubs-engine');
  await expect(page.locator('#prRows')).not.toBeEmpty();
  const total = Number(await page.locator('#prCount').innerText());
  expect(total).toBeGreaterThan(15);
  await page.locator('#pageSize').selectOption('15');

  const downloadEvent = page.waitForEvent('download');
  await page.locator('#export').click();
  const csv = await readDownload(await downloadEvent);
  const lines = csv.replace(/^\uFEFF/, '').trim().split(/\r?\n/);
  expect(lines[0]).toMatch(/^"仓库","PR"/);
  expect(lines[0]).not.toMatch(/^#/);
  expect(lines.length - 1).toBe(total);

  const notice = page.locator('.export-notice');
  await expect(notice).toContainText('实体：L 记录（PR）');
  await expect(notice).toContainText(`条数：${total}`);
  await expect(notice).toContainText('口径版本：ubs-pr-representative-v1');
  await expect(notice).toContainText('数据版本：sha256:60acaf');
});

test('S summary export declares its analysis scope and version', async ({ page }) => {
  await page.goto('./#ubs');
  await expect(page.locator('#repositoryRows')).not.toBeEmpty();
  const downloadEvent = page.waitForEvent('download');
  await page.locator('#exportRepositories').click();
  const csv = await readDownload(await downloadEvent);
  expect(csv.replace(/^\uFEFF/, '').split(/\r?\n/)[0]).toMatch(/^"仓库","采集状态"/);
  await expect(page.locator('.export-notice')).toContainText('实体：S 分析汇总');
  await expect(page.locator('.export-notice')).toContainText('分析范围：九仓跨仓汇总');
});

test('PR all-batch export from the detail binds the PR identity and batch count', async ({ page }) => {
  await page.goto('./#ubs/repo/ubs-engine');
  await expect(page.locator('#prRows tr[data-pr]').first()).toBeVisible();
  await page.locator('#prRows tr[data-pr]').first().click();
  await expect(page.locator('#detail')).toBeVisible();
  const downloadEvent = page.waitForEvent('download');
  await page.locator('#exportBatches').click();
  const csv = await readDownload(await downloadEvent);
  expect(csv.replace(/^\uFEFF/, '').split(/\r?\n/)[0]).toMatch(/^"仓库","PR","trigger"/);
  const notice = page.locator('#detail .export-notice');
  await expect(notice).toContainText('实体：PR 全部批次');
  await expect(notice).toContainText('分析范围：PR #');
});