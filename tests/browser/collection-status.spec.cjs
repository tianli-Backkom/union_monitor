const { test, expect } = require('@playwright/test');

// UDR-032-TC01: the collection-status workbench keeps three independent axes
// (task result / data version / data time). A failed round reusing old data
// stays failed + fallback with the ORIGINAL collected time; an unavailable
// project shows unavailable and an UNKNOWN concern count, never a fake zero.

function release(overrides) {
  const base = {
    schema_version: 1,
    release_id: 'rel-test',
    run_id: 'run-test',
    code_sha: 'a'.repeat(40),
    cutoff_at: '2026-10-11T01:14:59Z',
    published_at: '2026-10-11T01:18:38Z',
    schedule_time: null,
    release_status: 'verified',
    projects: {
      ubs: {
        task_status: 'success', data_mode: 'fresh',
        collected_at: '2026-10-11T01:14:59Z',
        window: { time_basis: 'pr_created_at', start_at: null, end_at: null },
        snapshot_version: 'sha256:u', snapshot_sha256: 'u'.repeat(64), validation_status: 'passed',
      },
      triton: {
        task_status: 'success', data_mode: 'fresh',
        collected_at: '2026-10-09T05:58:02Z',
        window: { time_basis: 'batch_started_at', start_at: '2026-10-06T05:52:57Z', end_at: '2026-10-09T05:52:57Z' },
        snapshot_version: null, snapshot_sha256: 't'.repeat(64), validation_status: 'passed',
      },
    },
  };
  for (const [pid, patch] of Object.entries(overrides || {})) {
    Object.assign(base.projects[pid], patch);
  }
  return base;
}

async function serveRelease(page, body) {
  await page.route('**/data/release.json*', route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }));
}

async function gotoWorkbench(page) {
  await page.goto('./#workbench');
  await expect(page.locator('#workbench-view')).toBeVisible();
}

function card(page, project) {
  return page.locator(`.project-card[data-project="${project}"]`);
}

test('workbench shows the three independent axes per project', async ({ page }) => {
  await gotoWorkbench(page);
  const ubs = card(page, 'ubs');
  await expect(ubs).toBeVisible();
  await expect(ubs).toContainText('openEuler UBS');
  await expect(ubs.locator('dt', { hasText: '本轮任务' }).locator('..')).toContainText('成功');
  await expect(ubs).toContainText('新数据');
  await expect(ubs).toContainText('720h · pr_created_at');
  const triton = card(page, 'triton');
  await expect(triton).toContainText('72h · batch_started_at');
  // Each enabled project gets one card, driven by the catalog not hardcoding.
  await expect(page.locator('.project-card')).toHaveCount(2);
});

test('failed round reusing old data stays failed + fallback with original time', async ({ page }) => {
  await serveRelease(page, release({
    ubs: { task_status: 'failed', data_mode: 'fallback', collected_at: '2026-10-09T01:00:00Z' },
  }));
  await gotoWorkbench(page);
  const ubs = card(page, 'ubs');
  await expect(ubs).toContainText('失败');
  await expect(ubs).toContainText('回退');
  // Fallback never reports a fresh collection time.
  await expect(ubs).toContainText('2026-10-09');
  await expect(ubs).not.toContainText('新数据');
});

test('unavailable project shows unavailable and unknown concern, not fake zero', async ({ page }) => {
  await serveRelease(page, release({
    triton: { task_status: 'failed', data_mode: 'unavailable' },
  }));
  await gotoWorkbench(page);
  const triton = card(page, 'triton');
  await expect(triton).toContainText('不可用');
  // Unknown concern count renders as em dash, never a fabricated zero.
  await expect(triton.locator('dt', { hasText: '关注' }).locator('..')).toContainText('—');
});

test('workbench stays catalog-driven when no release manifest is published', async ({ page }) => {
  // A missing release.json must not collapse the workbench into the legacy
  // fallback renderer: cards keep their project identity and show an explicit
  // unavailable status instead of fabricated success/zero states.
  await page.route('**/data/release.json*', route =>
    route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }));
  await gotoWorkbench(page);
  await expect(page.locator('.project-card')).toHaveCount(2);
  await expect(card(page, 'ubs')).toBeVisible();
  await expect(card(page, 'ubs')).toContainText('不可用');
  await expect(card(page, 'ubs').locator('dt', { hasText: '关注' }).locator('..')).toContainText('—');
});

test('project card navigates into the project overview', async ({ page }) => {
  await gotoWorkbench(page);
  await card(page, 'triton').locator('a[href="#projects/triton/overview"]').click();
  await expect(page.locator('#triton-view')).toBeVisible();
});
