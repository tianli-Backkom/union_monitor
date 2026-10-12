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