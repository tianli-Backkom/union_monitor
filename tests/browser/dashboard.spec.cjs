const {test,expect}=require('@playwright/test');

async function ready(page,hash='#ubs'){
  await page.goto('./'+hash);
  await expect(page.locator('#reload')).toBeEnabled();
  if(hash==='#triton')await expect(page.locator('#triton-view [data-role="kBatch"]')).toHaveText(/\d+/);
  if(hash==='#ubs')await expect(page.locator('#repositoryRows')).toContainText('ubs-engine');
}

test('published pages initialise without script exceptions',async({page})=>{
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await ready(page,'#ubs');
  await ready(page,'#triton');
  await page.locator('#reload').click();
  await expect(page.locator('#reload')).toBeEnabled();
  expect(errors).toEqual([]);
});

test('project links enter a project and legacy navigation clears the workbench',async({page})=>{
  await ready(page);
  await page.getByRole('link',{name:'工作台',exact:true}).click();
  await expect(page.locator('#workbench-view')).toBeVisible();
  await page.locator('a[href="#projects/triton/overview"]').click();
  await expect(page.locator('#triton-view')).toBeVisible();
  await expect(page.locator('#workbench-view')).toBeHidden();
  await page.getByRole('link',{name:'工作台',exact:true}).click();
  await page.locator('#sideProjectSelector').selectOption('triton');
  await expect(page.locator('#triton-view')).toBeVisible();
  await expect(page.locator('#workbench-view')).toBeHidden();
});

test('record search changes records while preserving analysis statistics',async({page})=>{
  await ready(page,'#triton');
  const before=await page.locator('#triton-view .kpi-grid').innerText();
  await page.getByRole('searchbox',{name:'搜索关注列表'}).fill('no-record-can-match-this-7c331');
  await expect(page.locator('#triton-view .row')).toHaveCount(0);
  await expect(page.locator('#triton-view [data-role="attention"]')).toContainText('当前没有匹配批次');
  expect(await page.locator('#triton-view .kpi-grid').innerText()).toBe(before);
  await page.getByRole('searchbox',{name:'搜索关注列表'}).fill('');
});

test('CSV download contains the selected records, independent of collapse',async({page})=>{
  await ready(page,'#triton');
  const downloadEvent=page.waitForEvent('download');
  await page.getByRole('button',{name:'导出批次 CSV',exact:true}).click();
  const download=await downloadEvent;
  expect(await download.failure()).toBeNull();
  const stream=await download.createReadStream();
  const chunks=[];for await(const chunk of stream)chunks.push(chunk);
  const csv=Buffer.concat(chunks).toString('utf8');
  const lines=csv.replace(/^\uFEFF/,'').trim().split(/\r?\n/);
  expect(lines[0]).toMatch(/^"pr","title","sha","base_branch",/);
  const payload=await page.evaluate(async()=>await (await fetch('data/triton.json')).json());
  expect(lines.length-1).toBe(payload.batches.length);
});

test('route changes close bound PR details and browser history restores the active view',async({page})=>{
  await ready(page,'#ubs');
  await page.locator('#exceptionRows .exception-row').first().click();
  await expect(page.locator('#detail')).toBeVisible();
  // Hash navigation while the native modal is open exercises owned-resource cleanup.
  await page.evaluate(()=>{location.hash='#workbench';});
  await expect(page.locator('#detail')).toBeHidden();
  await expect(page.locator('#workbench-view')).toBeVisible();
  await page.locator('#sideProjectSelector').selectOption('triton');
  await expect(page.locator('#triton-view')).toBeVisible();
  await page.goBack();
  await expect(page.locator('#workbench-view')).toBeVisible();
  await expect(page.locator('#triton-view')).toBeHidden();
  await page.goForward();
  await expect(page.locator('#triton-view')).toBeVisible();
  await expect(page.locator('#workbench-view')).toBeHidden();
});

test('failed snapshot reload keeps valid data and restores the control',async({page})=>{
  await ready(page,'#triton');
  const before=await page.locator('#triton-view .kpi-grid').innerText();
  await page.route('**/data/triton.json*',route=>route.fulfill({status:503,body:'unavailable'}));
  await page.locator('#reload').click();
  await expect(page.locator('[data-role="tritonError"]')).toContainText('503');
  await expect(page.locator('#reload')).toBeEnabled();
  expect(await page.locator('#triton-view .kpi-grid').innerText()).toBe(before);
});

test('mobile retains result and duration in complete batch records',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await ready(page,'#triton');
  await page.getByRole('button',{name:'查看全部批次',exact:true}).click();
  const row=page.locator('#triton-view .row-main').first();
  await expect(row.locator('.status')).toBeVisible();
  await expect(row.locator('.duration')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('keyboard opens a batch and Escape closes its pinned preview',async({page})=>{
  await ready(page,'#triton');
  const point=page.getByRole('button',{name:/E2E 详情/}).first();
  await point.press('Enter');
  await expect(page.locator('#triton-view [data-role="tip"]')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#triton-view [data-role="tip"]')).toBeHidden();
  await expect(point).toBeFocused();
});
