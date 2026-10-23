import {test, expect} from '@playwright/test';
import {mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';

const nav = (page, name) => page.getByRole('navigation').getByRole('button', {name, exact:true});
async function checked(page) {
  await page.goto('/');
  await page.getByLabel('Upload equipment dataset').setInputFiles('e2e/sample.csv');
  await page.getByRole('button', {name:'Check data', exact:true}).click();
  await expect(page.getByRole('button', {name:'Process and unlock'})).toBeVisible();
}
async function processed(page) {
  await checked(page);
  await page.getByRole('button', {name:'Process and unlock'}).click();
  await expect(page.getByRole('heading', {name:'Control tower', exact:true})).toBeVisible();
}

test('processing failure stays locked and supports retry', async ({page}) => {
  await checked(page);
  await page.route('**/api/datasets/process', route=>route.fulfill({status:500, contentType:'application/json', body:JSON.stringify({detail:'Processing failed. Retry your dataset.'})}));
  await page.getByRole('button', {name:'Process and unlock'}).click();
  await expect(page.getByRole('alert')).toContainText('Processing failed');
  await expect(nav(page,'Control tower')).toBeDisabled();
  await page.unroute('**/api/datasets/process');
  await page.getByRole('button', {name:'Process and unlock'}).click();
  await expect(nav(page,'Control tower')).toBeEnabled();
});

test('equipment request errors appear instead of an endless loading state', async ({page}) => {
  await processed(page);
  await nav(page,'Data setup').click();
  await page.route('**/api/equipment', route=>route.fulfill({status:503, contentType:'application/json', body:JSON.stringify({detail:'Equipment data unavailable. Try again.'})}));
  await nav(page,'Control tower').click();
  await expect(page.getByRole('alert')).toContainText('Equipment data unavailable');
});

test('alerts resolve and status filtering reflects the saved decision', async ({page}) => {
  await processed(page);
  await nav(page,'Alert triage').click();
  const row = page.getByRole('row').filter({has:page.getByRole('button',{name:'Resolve',exact:true})}).first();
  await row.getByRole('button',{name:'Resolve',exact:true}).click();
  await expect(page.getByRole('cell',{name:'Resolved',exact:true})).toHaveCount(1);
  await page.getByLabel('Status',{exact:true}).selectOption('Resolved');
  await expect(page.getByRole('cell',{name:'Resolved',exact:true})).toHaveCount(1);
  await expect(page.getByRole('button',{name:'Resolve',exact:true})).toHaveCount(0);
});

test('insufficient failure events show a validation message without invented metrics', async ({page}) => {
  await processed(page);
  await nav(page,'ML & data assurance').click();
  await page.getByRole('button',{name:'Train model',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Not enough failure events',{timeout:25000});
  await expect(page.getByTestId('kpi-Precision')).toHaveCount(0);
});

test('review screenshots and navigation contain no browser errors or emojis', async ({page}) => {
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  const directory=fileURLToPath(new URL('../../docs/previews/', import.meta.url));
  mkdirSync(directory,{recursive:true});
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Upload your equipment data'})).toBeVisible();
  await page.screenshot({path:join(directory,'upload-desktop.png'),fullPage:true});
  await processed(page);
  await expect(page.getByRole('cell',{name:'P-203',exact:true})).toBeVisible();
  await page.screenshot({path:join(directory,'overview-desktop.png'),fullPage:true});
  for(const name of ['Condition & diagnostics','Alert triage','Maintenance planning','ML & data assurance','Data setup']) {
    await nav(page,name).click();
    await expect(page.getByRole('heading',{name:name==='Data setup'?'Dataset':name,exact:true})).toBeVisible();
    expect(await page.locator('body').innerText()).not.toMatch(/[\p{Extended_Pictographic}\uFE0F]/u);
    if(name==='Condition & diagnostics') {
      await expect(page.getByRole('img',{name:'Sensor history'})).toBeVisible();
      await page.screenshot({path:join(directory,'equipment-desktop.png'),fullPage:true});
    }
  }
  await page.reload();
  await expect(page.getByRole('button',{name:'Clear dataset'})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await nav(page,'Control tower').click();
  await expect(page.getByRole('cell',{name:'P-203',exact:true})).toBeVisible();
  await page.screenshot({path:join(directory,'overview-mobile.png'),fullPage:true});
  expect(errors).toEqual([]);
});
