import {expect,test} from "@playwright/test";

test("打开、插入、预览并确认执行",async({page})=>{
  let previewCommands:any[]=[];
  const workspace={id:"workspace-1",revision_id:"revision-1",sheet_set:{name:"测试图纸集",sheet_count:1,subset_count:2,custom_properties:{项目号:"P-001"},subsets:[{id:"subset-1",name:"第一册",sheets:[{id:"sheet-1",number:"001",title:"平面图",custom_properties:{比例:"1:100"}}]},{id:"subset-2",name:"第二册",sheets:[]}]},diagnostics:[]};
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:workspace}));
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

test("失败任务显示逐 DWG 详情并可安全重试",async({page})=>{
  const workspace={id:"workspace-1",revision_id:"revision-1",sheet_set:{name:"测试集",sheet_count:0,subset_count:0,custom_properties:{},subsets:[]},diagnostics:[]};
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}]}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-failed",status:"FAILED",progress:40,attempt:1,error_code:"CAD_TIMEOUT",suggestion:"检查 CAD 日志",files:[{target_path:"A.dwg",status:"FAILED",progress:0,duration_ms:600000,error_code:"CAD_TIMEOUT"}]}}));
  await page.route("**/api/jobs/job-failed/retry",route=>route.fulfill({json:{id:"job-failed",status:"QUEUED",progress:0,attempt:1,files:[]}}));
  await page.goto("/");
  await page.getByPlaceholder("输入 .dst 绝对路径").fill("C:\\project\\test.dst");
  await page.getByRole("button",{name:"打开项目"}).click();
  await page.getByRole("button",{name:"更新图纸集"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  page.once("dialog",dialog=>dialog.accept());
  await page.getByRole("button",{name:"确认并执行"}).click();
  await expect(page.getByText("CAD_TIMEOUT").first()).toBeVisible();
  await expect(page.getByText("A.dwg")).toBeVisible();
  await expect(page.getByText("检查 CAD 日志")).toBeVisible();
  await page.getByRole("button",{name:"安全重试"}).click();
  await expect(page.getByText(/QUEUED/)).toBeVisible();
});

test("修订恢复先预览再确认为新修订",async({page})=>{
  const workspace={id:"workspace-1",revision_id:"revision-2",sheet_set:{name:"测试集",sheet_count:0,subset_count:0,custom_properties:{},subsets:[]},diagnostics:[]};
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:workspace}));
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));
  await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));
  await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore",route=>route.fulfill({json:{id:"restore-1",status:"SUCCEEDED",progress:100,attempt:0,files:[]}}));
  await page.goto("/");
  await page.getByPlaceholder("输入 .dst 绝对路径").fill("C:\\project\\test.dst");
  await page.getByRole("button",{name:"打开项目"}).click();
  await page.getByRole("button",{name:"修订历史"}).click();
  await page.getByRole("button",{name:"恢复预览"}).click();
  await expect(page.getByText("replace test.dst")).toBeVisible();
  page.once("dialog",dialog=>dialog.accept());
  await page.getByRole("button",{name:"恢复为新修订"}).click();
  await expect(page.locator(".summary input")).toHaveValue("测试集");
});
