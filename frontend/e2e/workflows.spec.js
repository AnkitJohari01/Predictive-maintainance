import {test, expect} from '@playwright/test';

const nav = (page, name) => page.getByRole('navigation').getByRole('button', {name, exact: true});
async function upload(page, file = 'e2e/sample.csv') {
  await page.goto('/');
  await page.getByLabel('Upload equipment dataset').setInputFiles(file);
  await page.getByRole('button', {name: 'Check data', exact: true}).click();
  await expect(nav(page, 'Control tower')).toBeDisabled();
  await page.getByRole('button', {name: 'Process and unlock'}).click();
  await expect(page.getByRole('heading', {name: 'Control tower', exact: true})).toBeVisible();
}

test('status filter and empty results use the uploaded equipment', async ({page}) => {
  await upload(page);
  await page.getByLabel('Equipment status').selectOption('critical');
  await expect(page.getByRole('cell', {name: 'P-203', exact: true})).toBeVisible();
  await expect(page.getByRole('cell', {name: 'T-005', exact: true})).toHaveCount(0);
  await page.getByLabel('Search equipment').fill('unknown');
  await expect(page.getByText('No equipment matches', {exact: false})).toBeVisible();
});

test('equipment chart exposes real readings and supports switching sensors', async ({page}) => {
  await upload(page);
  await nav(page, 'Condition & diagnostics').click();
  await expect(page.getByRole('img', {name: 'Sensor history'})).toBeVisible();
  const slider = page.getByRole('slider', {name: 'Reading in sensor history'});
  await slider.focus();
  await slider.press('End');
  await expect(page.getByTestId('chart-reading')).toContainText('UTC');
  await expect(page.getByTestId('chart-reading')).toContainText('6.57');
  await slider.press('Home');
  await expect(page.getByTestId('chart-reading')).toContainText('1.93');
  await page.getByRole('button', {name: 'bearing_temp_c', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'bearing_temp_c', exact: true})).toBeVisible();
  await page.getByLabel('Equipment', {exact: true}).selectOption('CV-08');
  await expect(page.getByRole('img', {name: 'Sensor history'})).toBeVisible();
});

test('work order lifecycle updates the overview count', async ({page}) => {
  await upload(page);
  await nav(page, 'Maintenance planning').click();
  await page.getByRole('button', {name: 'Create work order', exact: true}).first().click();
  await expect(page.getByLabel('Assignee').first()).toBeVisible();
  await page.getByLabel('Assignee').first().fill('Maintenance team');
  await page.getByLabel('Assignee').first().press('Tab');
  await expect(page.getByLabel('Assignee').first()).toHaveValue('Maintenance team');
  await page.getByLabel('Due date').first().fill('2026-12-01');
  await page.getByLabel('Status', {exact: true}).first().selectOption('Done');
  await expect(page.getByLabel('Status', {exact: true}).first()).toHaveValue('Done');
  await nav(page, 'Control tower').click();
  await expect(page.getByTestId('kpi-Open work orders')).toContainText('0');
});

test('invalid mapping cannot unlock analytics and can be corrected', async ({page}) => {
  await page.goto('/');
  await page.getByLabel('Upload equipment dataset').setInputFiles('e2e/sample.csv');
  await page.getByLabel('Timestamp', {exact: true}).selectOption('machine_id');
  await page.getByRole('button', {name: 'Check data', exact: true}).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(nav(page, 'Control tower')).toBeDisabled();
  await page.getByLabel('Timestamp', {exact: true}).selectOption('timestamp');
  await page.getByRole('button', {name: 'Check data', exact: true}).click();
  await page.getByRole('button', {name: 'Process and unlock'}).click();
  await expect(nav(page, 'Control tower')).toBeEnabled();
});

test('empty and too-small files show actionable errors', async ({page}) => {
  await page.goto('/');
  await page.getByLabel('Upload equipment dataset').setInputFiles({name: 'empty.csv', mimeType: 'text/csv', buffer: Buffer.from('timestamp,machine_id,vibration\n')});
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(nav(page, 'Control tower')).toBeDisabled();
  await page.getByLabel('Upload equipment dataset').setInputFiles({name: 'small.csv', mimeType: 'text/csv', buffer: Buffer.from('timestamp,machine_id,vibration\n2026-01-01,A,2\n')});
  await page.getByLabel('Timestamp', {exact: true}).selectOption('timestamp');
  await page.getByLabel('Equipment ID', {exact: true}).selectOption('machine_id');
  await page.getByRole('button', {name: 'Check data', exact: true}).click();
  await expect(page.getByRole('alert')).toContainText('20');
});

test('failed replacement keeps active analytics and valid replacement resets work', async ({page}) => {
  await upload(page);
  await nav(page, 'Data setup').click();
  await page.getByLabel('Upload equipment dataset').setInputFiles({name: 'bad.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.from('not excel')});
  await expect(page.getByRole('alert')).toBeVisible();
  await nav(page, 'Control tower').click();
  await expect(page.getByRole('cell', {name: 'P-203', exact: true})).toBeVisible();
  await nav(page, 'Data setup').click();
  const csv = 'timestamp,machine_id,pressure\n' + Array.from({length:30}, (_,i)=>`2026-09-${String(i+1).padStart(2,'0')},NEW-01,${10+i%3}`).join('\n');
  await page.getByLabel('Upload equipment dataset').setInputFiles({name: 'new.csv', mimeType: 'text/csv', buffer: Buffer.from(csv)});
  await page.getByRole('button', {name: 'Check data', exact: true}).click();
  await page.getByRole('button', {name: 'Process and unlock'}).click();
  await expect(page.getByRole('cell', {name: 'NEW-01', exact: true})).toBeVisible();
  await expect(page.getByRole('cell', {name: 'P-203', exact: true})).toHaveCount(0);
  await nav(page, 'ML & data assurance').click();
  await page.getByRole('button', {name: 'Train model', exact: true}).click();
  await expect(page.getByText('No failure labels, so accuracy cannot be measured.', {exact:false})).toBeVisible({timeout:25000});
});

test('server dataset loss relocks navigation', async ({page, request}) => {
  await upload(page);
  const sid = await page.evaluate(() => localStorage.getItem('sid'));
  await request.delete('http://127.0.0.1:8000/api/dataset', {headers:{'X-Session':sid}});
  await nav(page, 'Alert triage').click();
  await expect(page.getByRole('heading', {name:'Upload your equipment data'})).toBeVisible();
  await expect(nav(page, 'Control tower')).toBeDisabled();
});

test('mobile uploaded workflow fits the viewport and remains emoji-free', async ({page}) => {
  await page.setViewportSize({width:390, height:844});
  await upload(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await nav(page, 'Condition & diagnostics').click();
  await expect(page.getByRole('img', {name:'Sensor history'})).toBeVisible();
  expect(await page.locator('body').innerText()).not.toMatch(/[\p{Extended_Pictographic}\uFE0F]/u);
});
