const { test, expect } = require('@playwright/test');

// UDR-015: one catalog-driven fixed-task navigation (not per-community menus).
// The project selector and fixed tasks come from the catalog; switching projects
// re-scopes task links and isolates per-project conditions; an unsupported task
// explains the reason instead of faking a view or KPI.

async function readyWorkbench(page) {
  await page.goto('./#workbench');
  await expect(page.locator('#workbench-view')).toBeVisible();
  await expect(page.locator('#sideProjectSelector option')).toHaveCount(2);
}

test('fixed tasks come from the catalog, with no per-community top-level menus', async ({ page }) => {
  await readyWorkbench(page);
  const options = await page.locator('#sideProjectSelector option').allTextContents();
  expect(options).toEqual(['openEuler UBS', 'Triton-Ascend']);
  const navText = await page.locator('#sideTasks').innerText();
  for (const label of ['项目概览', '趋势与任务', 'PR 与批次', '数据质量', '数据与采集', '指标说明']) {
    expect(navText).toContain(label);
  }
  await expect(page.locator('.nav-group', { hasText: 'openEuler UBS' })).toHaveCount(0);
  await expect(page.locator('.nav-group', { hasText: 'Triton-Ascend' })).toHaveCount(0);
});

test('selecting a project re-scopes the fixed-task links and navigates', async ({ page }) => {
  await readyWorkbench(page);
  await page.locator('#sideProjectSelector').selectOption('triton');
  await expect(page.locator('#triton-view')).toBeVisible();
  await expect(page.locator('#sideTasks a[data-task="records"]'))
    .toHaveAttribute('href', '#projects/triton/records');
  await page.locator('#sideTasks a[data-task="trends"]').click();
  await expect(page.locator('#triton-view')).toBeVisible();
  await expect(page.locator('#sideTasks a[data-task="trends"]')).toHaveClass(/active/);
});

test('switching projects does not leak UBS conditions into Triton and restores them back', async ({ page }) => {
  await page.goto('./#ubs/repo/ubs-engine');
  await expect(page.locator('#prRows')).not.toBeEmpty();
  await page.locator('#state').selectOption('merged');
  await page.locator('#sideProjectSelector').selectOption('triton');
  await expect(page.locator('#triton-view')).toBeVisible();
  await expect(page.locator('#state')).toBeHidden();
  await page.locator('#sideProjectSelector').selectOption('ubs');
  await expect(page.locator('#state')).toHaveValue('merged');
});

test('an unsupported task explains the reason instead of faking a view', async ({ page }) => {
  await page.goto('./#projects/triton/quality');
  await expect(page.locator('#project-task-view')).toBeVisible();
  await expect(page.locator('#project-task-view')).toContainText('未提供');
  await expect(page.locator('#triton-view')).toBeHidden();
});