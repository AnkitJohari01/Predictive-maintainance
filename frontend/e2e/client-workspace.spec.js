import {test, expect} from '@playwright/test';

const nav=(page,name)=>page.getByRole('navigation').getByRole('button',{name,exact:true});
const bundle=()=>({
  telemetry:['P-104','P-118'].flatMap(asset_id=>Array.from({length:30},(_,i)=>({timestamp:`2026-09-${String(i+1).padStart(2,'0')}T06:00:00Z`,asset_id,vibration_mm_s:2+(i%3)*.02+(i>22?(i-22)*.4:0)}))),sensors:['vibration_mm_s'],
  assets:['P-104','P-118'].map(asset_id=>({asset_id,name:'Cooling pump '+asset_id,site:'Plant A',criticality:'A',owner:'Planner',part_id:'BRG',part_qty:1,repair_hours:2,skill:'Mechanical',operating_hours:100,observation_start:'2026-09-01',observation_end:'2026-10-01'})),
  parts:[{part_id:'BRG',description:'Bearing',on_hand:1,reserved:0,lead_days:3,unit_cost:100}],
  windows:['P-104','P-118'].map(asset_id=>({window_id:'W-'+asset_id,asset_id,start:'2026-10-02T08:00:00Z',end:'2026-10-02T12:00:00Z',crew_count:1,required_crew:1,crew_skill:'Mechanical',resource_pool_id:'POOL-1'})),
  documents:[{document_id:'DOC-1',title:'Pump inspection',revision:'A',section:'2',asset_class:'All',text:'Inspect bearing with comparable rpm and load.'}],
  dependencies:[{from_asset:'P-104',to_asset:'P-118',service:'Cooling'}],
  changes:[{change_id:'C-1',asset_id:'P-104',timestamp:'2026-09-20',description:'Lubrication changed; cause unconfirmed'}],
  failures:[{event_id:'F-1',asset_id:'P-104',failed_at:'2026-09-10T06:00:00Z',restored_at:'2026-09-10T10:00:00Z',failure_mode:'Bearing',corrective_action:'Replacement'}]
});
async function load(page){await page.goto('/');await page.getByLabel('Upload equipment dataset').setInputFiles({name:'workspace.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bundle()))});await expect(page.getByRole('heading',{name:'Control tower',exact:true})).toBeVisible();}

test('complete bundle drives persistent case, reservations, approval and verified outcome',async({page})=>{
 await load(page);
 await expect(page.getByRole('heading',{name:'Today’s action desk'})).toBeVisible();
 await page.getByRole('button',{name:'Open case workspace',exact:true}).first().click();
 await page.getByLabel('Case equipment').selectOption('P-104');
 await page.getByLabel('Accountable owner',{exact:true}).fill('Meera');
 await page.getByLabel('Inspection disposition').selectOption('Confirmed component issue');
 await page.getByLabel('Inspection findings').fill('Bearing inspected at the recorded load.');
 await page.getByRole('button',{name:'Save investigation',exact:true}).click();
 await page.getByRole('button',{name:'Reserve listed materials',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('reserve');
 await page.getByLabel('Case equipment').selectOption('P-118');
 await page.getByRole('button',{name:'Reserve listed materials',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Insufficient unreserved stock');
 await page.getByLabel('Case equipment').selectOption('P-104');
 await page.getByLabel('Work scope reviewed').check();await page.getByLabel('Production impact reviewed').check();await page.getByLabel('Permit prerequisites reviewed').check();
 await page.getByRole('button',{name:'Approve work proposal',exact:true}).click();
 await expect(page.getByText('Approved proposal',{exact:true}).first()).toBeVisible();
 await page.reload();await nav(page,'Alert triage').click();
 await page.getByLabel('Case equipment').selectOption('P-104');
 await expect(page.getByLabel('Accountable owner',{exact:true})).toHaveValue('Meera');
 await page.getByLabel('Verification reading',{exact:true}).fill('2.1');
 await page.getByLabel('Verification time (UTC)').fill('2026-10-02T11:00');
 await page.getByLabel('Verification conditions').fill('Same rpm and load, calibrated instrument.');
 await page.getByRole('button',{name:'Verify and close case',exact:true}).click();
 await expect(page.getByText('Verified',{exact:true}).first()).toBeVisible();
 await expect(page.getByRole('row').filter({has:page.getByRole('cell',{name:'P-104',exact:true})}).getByRole('cell',{name:'Resolved',exact:true})).toBeVisible();
 await page.screenshot({path:'../docs/previews/client-case-desktop.png',fullPage:true});
 await nav(page,'Reliability & impact').click();await expect(page.getByText('Same rpm and load, calibrated instrument.')).toBeVisible();
});

test('scenarios and source search use uploaded context',async({page})=>{
 await load(page);await nav(page,'What-if analysis').click();
 await page.getByLabel('Assumed demand (units/hour)').fill('80');await page.getByLabel('Standby-supported capacity (units/hour)').fill('60');
 await page.getByRole('button',{name:'Compare scenario',exact:true}).click();
 await expect(page.getByTestId('scenario-shortfall')).toContainText('40');
 await nav(page,'Maintenance knowledge').click();await page.getByLabel('Search reference evidence').fill('bearing');await page.getByRole('button',{name:'Search sources'}).click();
 await expect(page.getByText('DOC-1',{exact:false}).first()).toBeVisible();
 await page.getByLabel('Search reference evidence').fill('absent');await page.getByRole('button',{name:'Search sources'}).click();await expect(page.getByText('No matching sources.')).toBeVisible();
});

test('all approved sections fit mobile and invalid bundle retains prior data',async({page})=>{
 await load(page);await nav(page,'Data setup').click();const bad=bundle();bad.parts[0].reserved=9;
 await page.getByLabel('Upload equipment dataset').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bad))});
 await expect(page.getByRole('alert').first()).toContainText('Reserved stock');
 await page.setViewportSize({width:390,height:850});
 for(const name of ['Control tower','Asset intelligence','Condition & diagnostics','Alert triage','Maintenance planning','Parts readiness','Reliability & impact','What-if analysis','Maintenance knowledge','ML & data assurance','Research & scope']){
  await nav(page,name).click();await expect(page.locator('#main-content')).toBeVisible();
  const bounds=await page.locator('body').evaluate(e=>({scroll:e.scrollWidth,width:e.clientWidth}));expect(bounds.scroll).toBeLessThanOrEqual(bounds.width+1);
 }
 await page.screenshot({path:'../docs/previews/client-workspace-mobile.png',fullPage:true});
});
