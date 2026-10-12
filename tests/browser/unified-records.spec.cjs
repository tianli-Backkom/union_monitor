const { test, expect } = require('@playwright/test');

// UDR-018-TC01: page length 15/30/50 slices a stable, complete sequence with
// no loss. The displayed range end is always min(pageSize, total), and
// changing the page length resets to page 1.

async function readyRepo(page, hash = '#ubs/repo/ubs-engine') {
  await page.goto('./' + hash);
  await expect(page.locator('#reload')).toBeEnabled();
  await expect(page.locator('#prRows')).not.toBeEmpty();
}

async function total(page) {
  return Number(await page.locator('#prCount').innerText());
}

test('page length selector shows 15/30/50 and re-slices without loss', async ({ page }) => {
  await readyRepo(page);
  const sel = page.locator('#pageSize');
  await expect(sel).toBeVisible();
  await expect(sel.locator('option')).toHaveText(['15', '30', '50']);
  const n = await total(page);
  expect(n).toBeGreaterThan(0);

  for (const size of [15, 30, 50]) {
    await sel.selectOption(String(size));
    await expect(page.locator('#rowInfo')).toContainText(`1–${Math.min(size, n)}`);
    await expect(page.locator('#rowInfo')).toContainText(`/ ${n} 条`);
  }
});

test('changing page length resets to page 1', async ({ page }) => {
  await readyRepo(page);
  const n = await total(page);
  if (n <= 15) test.skip(true, 'needs more than 15 records to exercise pagination');
  await page.locator('#next').click();
  await expect(page.locator('#pageInfo')).toContainText('2 /');
  await page.locator('#pageSize').selectOption('30');
  await expect(page.locator('#pageInfo')).toContainText('1 /');
});

test('records default to batches and the entity toggle switches back to PR', async ({ page }) => {
  await readyRepo(page);
  // Default entity is batch (UDR-018).
  await expect(page.locator('#entity')).toHaveValue('batches');
  await expect(page.locator('#recordTitle')).toHaveText('批次效率明细');
  await expect(page.locator('#prRows tr[data-batch]').first()).toBeVisible();
  // Toggle to PR: batch rows disappear, PR rows appear, count label flips.
  await page.locator('#entity').selectOption('prs');
  await expect(page.locator('#recordTitle')).toHaveText('PR 效率明细');
  await expect(page.locator('#prRows tr[data-batch]')).toHaveCount(0);
  await expect(page.locator('#prRows tr[data-pr]').first()).toBeVisible();
  // Back to batches.
  await page.locator('#entity').selectOption('batches');
  await expect(page.locator('#prRows tr[data-batch]').first()).toBeVisible();
});

// UDR-018-TC01: Triton also uses the common batch records task — the same
// records model (Records.tritonBatchRecords) drives a Triton batch list with
// the same stable sort-before-pagination control, so both projects share one
// records task instead of a bespoke Triton table.
test('triton records task renders the common batch records model', async ({ page }) => {
  await page.goto('./#projects/triton/records');
  await expect(page.locator('#reload')).toBeEnabled();
  await expect(page.locator('#triton-view')).toBeVisible();
  await expect(page.locator('#triton-view h2')).toContainText('批次记录');
  await expect(page.locator('#crumb')).toContainText('批次记录');
  await expect(page.locator('#triton-view tr[data-batch]').first()).toBeVisible();
  const n = Number(await page.locator('#triton-view .count').innerText());
  expect(n).toBeGreaterThan(0);
  for (const size of [15, 30, 50]) {
    await page.locator('#triton-view [data-role="pageSize"]').selectOption(String(size));
    await expect(page.locator('#triton-view [data-role="rowInfo"]')).toContainText(`1–${Math.min(size, n)}`);
    await expect(page.locator('#triton-view [data-role="rowInfo"]')).toContainText(`/ ${n} 条`);
  }
});