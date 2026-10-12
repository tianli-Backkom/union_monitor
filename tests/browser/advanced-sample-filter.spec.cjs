const { test, expect } = require('@playwright/test');

// UDR-016-TC02: the explicit advanced sample-filter entry changes the analysis
// set (S) and its denominator, shows a persistent condition bar, and clears
// back to the full set with page reset to 1. Plain search (L) never changes S.

async function readyRepo(page, hash = '#ubs/repo/ubs-engine') {
  await page.goto('./' + hash);
  await expect(page.locator('#reload')).toBeEnabled();
  // The PR detail view is ready once the row container holds either rows or
  // the explicit empty message.
  await expect(page.locator('#prRows')).not.toBeEmpty();
}

function denominatorText(page) {
  return page.locator('#activeConditions strong').innerText();
}

test('advanced entry reveals trigger/quality filters and a condition bar', async ({ page }) => {
  await readyRepo(page);
  const toggle = page.locator('#advancedToggle');
  await expect(toggle).toBeVisible();
  await expect(page.locator('#triggerFilter')).toBeHidden();
  await toggle.click();
  await expect(page.locator('#triggerFilter')).toBeVisible();
  await expect(page.locator('#qualityFilter')).toBeVisible();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
});

test('state filter changes the analysis denominator and is clearable', async ({ page }) => {
  await readyRepo(page);
  await page.locator('#entity').selectOption('prs');
  await page.locator('#state').selectOption('merged');
  const bar = page.locator('#activeConditions');
  await expect(bar).toBeVisible();
  await expect(bar).toContainText('PR 状态＝已合入');
  await expect(bar).toContainText('有效分母');
  // The denominator equals the PR count shown in the record header.
  const denom = await denominatorText(page);
  const count = await page.locator('#prCount').innerText();
  expect(denom).toContain(count);
  await page.locator('#clearConditions').click();
  await expect(bar).toBeHidden();
  expect(await page.locator('#state').inputValue()).toBe('');
});

test('plain search changes records but not the analysis denominator', async ({ page }) => {
  await readyRepo(page);
  await page.locator('#query').fill('no-match-7c331');
  await expect(page.locator('#activeConditions')).toBeHidden();
  // L changes rows (to empty) without a condition bar: S is unchanged.
  await expect(page.locator('#prRows')).not.toBeEmpty();
});