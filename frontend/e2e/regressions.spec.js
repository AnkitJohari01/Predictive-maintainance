import {test,expect} from "@playwright/test";

const nav=(page,name)=>page.getByRole("navigation").getByRole("button",{name,exact:true});
async function load(page,file="e2e/sample.csv",expectOverview=true){
  await page.goto("/");
  await page.locator("input[type=file]").setInputFiles(file);
  await page.getByRole("button",{name:"Check data",exact:true}).click();
  await page.getByRole("button",{name:"Process and unlock"}).click();
  if(expectOverview)await expect(page.getByRole("heading",{name:"Overview",exact:true})).toBeVisible();
}

test("overview displays an equipment API failure",async({page})=>{
  await page.route("**/api/equipment",route=>route.fulfill({status:503,json:{detail:"Equipment temporarily unavailable"}}));
  await load(page,"e2e/sample.csv",false);
  await expect(page.getByRole("alert")).toContainText("Equipment temporarily unavailable");
});

test("a late equipment response cannot replace the selected equipment",async({page})=>{
  await load(page);
  let release,started;
  const gate=new Promise(resolve=>release=resolve),intercepted=new Promise(resolve=>started=resolve);
  await page.route("**/api/equipment/P-203",async route=>{
    const response=await route.fetch();started();await gate;await route.fulfill({response});
  });
  await nav(page,"Equipment Monitor").click();
  await intercepted;
  await page.getByLabel("Equipment",{exact:true}).selectOption("CV-08");
  await expect(page.getByRole("heading",{name:"bearing_temp_c",exact:true})).toBeVisible();
  const late=page.waitForResponse(r=>r.url().endsWith("/api/equipment/P-203"));
  release();await late;
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  await expect(page.getByRole("heading",{name:"bearing_temp_c",exact:true})).toBeVisible();
});

test("sensor charts show the lower critical boundary for downward shifts",async({page})=>{
  await load(page);await nav(page,"Equipment Monitor").click();
  await page.getByLabel("Equipment",{exact:true}).selectOption("C-07");
  await expect(page.getByText("Critical threshold (baseline − 3σ)",{exact:true})).toBeVisible();
});

test("sensor selector exposes which sensor is active",async({page})=>{
  await load(page);await nav(page,"Equipment Monitor").click();
  const pressure=page.getByRole("button",{name:"pressure_bar",exact:true});
  await pressure.click();
  await expect(pressure).toHaveAttribute("aria-pressed","true");
  await expect(page.getByRole("button",{name:"vibration_mm_s",exact:true})).toHaveAttribute("aria-pressed","false");
});

test("health summary includes machines without enough readings",async({page})=>{
  const rows=["timestamp,machine_id,vibration"];
  for(let i=0;i<20;i++)rows.push(`2026-01-${String(i+1).padStart(2,"0")},${i<9?"A":"B"},${i%2?101:99}`);
  await load(page,{name:"sparse.csv",mimeType:"text/csv",buffer:Buffer.from(rows.join("\n"))});
  const label=page.getByText("Health (critical / watch / healthy / not scored)",{exact:true});
  await expect(label).toBeVisible();
  await expect(label.locator("..")).toContainText(/0\s*\/\s*0\s*\/\s*1\s*\/\s*1/);
});

test("maintenance edits persist and completion updates the overview count",async({page})=>{
  await load(page);await nav(page,"Maintenance").click();
  await page.getByRole("button",{name:"Create work order"}).first().click();
  await page.getByLabel("Assignee",{exact:true}).fill("QA owner");
  await page.getByRole("heading",{name:"Maintenance",exact:true}).click();
  await expect.poll(async()=>page.getByLabel("Assignee",{exact:true}).inputValue()).toBe("QA owner");
  await page.getByLabel("Due date",{exact:true}).fill("2026-11-01");
  await page.getByLabel("Status",{exact:true}).selectOption("Done");
  await nav(page,"Overview").click();
  await expect(page.getByText("Open work orders",{exact:true}).locator("..").locator("b")).toHaveText("0");
  await nav(page,"Maintenance").click();
  await expect(page.getByLabel("Assignee",{exact:true})).toHaveValue("QA owner");
  await expect(page.getByLabel("Due date",{exact:true})).toHaveValue("2026-11-01");
  await expect(page.getByLabel("Status",{exact:true})).toHaveValue("Done");
});
