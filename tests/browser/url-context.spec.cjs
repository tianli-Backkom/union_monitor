const { test, expect } = require('@playwright/test');

// UDR-020: the records list state (S/L conditions, sort, page size, page)
// round-trips through the #projects/ubs/{records|quality} query. Confirmed
// control changes push a history entry; a shared/refreshed URL restores the
// same controls and list.

async function readyRepo(page, hash = '#ubs/repo/ubs-engine') {
  await page.goto('./' + hash);
  await expect(page.locator('#reload')).toBeEnabled();
  await expect(page.locator('#prRows')).not.toBeEmpty();
}

test('confirmed changes push into the query and a shared URL restores the controls', async ({ page, context }) => {
  await readyRepo(page);
  await page.locator('#entity').selectOption('prs');
  await page.locator('#state').selectOption('merged');
  await page.locator('#sort').selectOption('batches');
  await page.locator('#pageSize').selectOption('30');

  const url = page.url();
  expect(url).toContain('#projects/ubs/records');
  expect(url).toContain('state=merged');
  expect(url).toContain('sort=batches');
  expect(url).toContain('ps=30');

  const shared = await context.newPage();
  await shared.goto(url);
  await expect(shared.locator('#prRows')).not.toBeEmpty();
  await expect(shared.locator('#state')).toHaveValue('merged');
  await expect(shared.locator('#sort')).toHaveValue('batches');
  await expect(shared.locator('#pageSize')).toHaveValue('30');
  await shared.close();
});

test('plain search replaces the URL as the user types, without a condition bar', async ({ page }) => {
  await readyRepo(page);
  await page.locator('#query').fill('ubs-engine');
  await expect(page.locator('#activeConditions')).toBeHidden();
  await expect(page.locator('#prRows')).not.toBeEmpty();
  expect(page.url()).toContain('q=ubs-engine');
});

test('opening and closing a detail carries its identity in the URL', async ({ page }) => {
  await readyRepo(page);
  const firstPr = await page.locator('#prRows tr[data-pr]').first().getAttribute('data-pr');
  await page.locator('#prRows tr[data-pr]').first().click();
  await expect(page.locator('#detail')).toBeVisible();
  expect(page.url()).toContain(`pr=${firstPr}`);
  await page.locator('#closeDetail').click();
  await expect(page.locator('#detail')).toBeHidden();
  expect(page.url()).not.toContain('pr=');
});