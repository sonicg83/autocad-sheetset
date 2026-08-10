import {expect,test} from "@playwright/test";

test("打开、插入、预览并确认执行",async({page})=>{
  let previewCommands:any[]=[];
  const workspace={id:"workspace-1",revision_id:"revision-1",sheet_set:{name:"测试图纸集",sheet_count:1,subset_count:2,custom_properties:{项目号:"P-001"},subsets:[{id:"subset-1",name:"第一册",sheets:[{id:"sheet-1",number:"001",title:"平面图",custom_properties:{比例:"1:100"}}]},{id:"subset-2",name:"第二册",sheets:[]}]},diagnostics:[]};
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewCommands=(await route.request().postDataJSON()).commands;await route.fulfill({json:{executable:true,requires_cad:true,changes:previewCommands,affected_files:["test.dst","A.dwg"]}})});
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-1",status:"SUCCEEDED",progress:100}}));
  await page.goto("/");
  await page.getByPlaceholder("输入 .dst 绝对路径").fill("C:\\project\\test.dst");
  await page.getByRole("button",{name:"打开项目"}).click();
  await expect(page.locator(".summary input")).toHaveValue("测试图纸集");
  await page.getByPlaceholder("来源DWG/DWT绝对路径").fill("C:\\template.dwt");
  await page.getByPlaceholder("来源布局名").fill("A1模板");
  await page.getByPlaceholder("图号").fill("002");
  await page.getByPlaceholder("标题").fill("新增图");
  await page.getByRole("button",{name:"加入新增命令"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  await expect(page.getByText("完整变更预览")).toBeVisible();
  expect(previewCommands).toHaveLength(1);
  page.once("dialog",dialog=>dialog.accept());
  await page.getByRole("button",{name:"确认并执行"}).click();
  await expect(page.getByText("任务 job-1")).toBeVisible();
});
