---
id: PLAN-INT-001
title: 双项目文档迁移实施计划
status: proposed
owners:
  - integration
created: 2026-08-17
updated: 2026-08-17
related:
  - ARCH-INT-001
---

# 双项目文档迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有平铺文档迁移为 Legacy Python 重构、DST Manager、公共能力和跨项目整合四个清晰范围，并建立可持续维护的索引、模板、状态和验证规则。

**Architecture:** 迁移采用项目优先的混合结构，先建立不会产生断链的治理入口，再按 Legacy、DST Manager、共享能力三个独立批次移动文档，最后统一收口仓库入口和链接。现有大型设计文档只增加元数据并作为 `architecture-baseline` 迁移，不在本计划中拆写其历史正文。

**Tech Stack:** Markdown、YAML front matter、Git、PowerShell 7/Windows PowerShell 5.1 兼容命令、RTK。

## Global Constraints

- 始终使用简体中文编写文档、注释、变更记录和 Git commit message；协议字段和固定英文名称保持原样。
- 所有文本文件使用 UTF-8；不得修改 `legacy/`、`sample/` 或其中的私有原件。
- 长期知识进入 `docs/`；路线图、实施计划、待办和备忘进入 `.planning/`。
- `shared/` 只接收已被两条产品线采用的能力；未来可能共享但尚未采用的内容继续归属原项目。
- `integration/` 只保存跨项目契约、整合提案、整合架构和整合决策。
- 只移动和补充文档，不修改应用行为、Python 依赖、Web 依赖、数据库或 AutoCAD 插件。
- 使用 `apply_patch` 修改文本；使用 `git mv` 保留现有文件历史。
- 每个任务只暂存本任务文件，完成验证后使用简体中文 commit message 提交。
- 历史 `changelog.md` 条目中的旧路径保持原样，以保存当时事实；当前入口、AGENTS 指令和文档正文链接必须指向新路径。

---

## 文件结构与职责

本计划创建或迁移以下有效文件；`archive/` 和尚无内容的子目录在首次需要时创建，不提交空目录占位文件。

```text
docs/
├─ README.md                                      # 全仓长期文档入口
├─ _templates/                                   # 正式长期文档模板
├─ legacy-refactor/                              # 旧生成工具现代化重构
├─ dst-manager/                                  # DST Manager 产品线
├─ shared/                                       # 已确认复用的知识与契约
└─ integration/                                  # 跨项目治理与整合

.planning/
├─ README.md                                     # 执行性资料入口和归档规则
├─ _templates/                                   # 路线图、计划、备忘模板
├─ roadmaps/                                     # 三条当前路线
└─ plans/                                        # 可执行计划
```

正式文档 ID 和目标路径固定如下：

| ID | 状态 | 创建日期 | 目标路径 |
| --- | --- | --- | --- |
| `ARCH-LR-001` | `accepted` | `2026-08-10` | `docs/legacy-refactor/architecture/ARCH-LR-001-modern-python-refactor-baseline.md` |
| `RES-LR-001` | `accepted` | `2026-07-15` | `docs/legacy-refactor/research/RES-LR-001-python-refactor-assessment.md` |
| `GUIDE-LR-001` | `accepted` | `2026-07-15` | `docs/legacy-refactor/guides/GUIDE-LR-001-legacy-development-handover.md` |
| `ARCH-DM-001` | `accepted` | `2026-08-10` | `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md` |
| `PLAN-DM-001` | `completed` | `2026-08-11` | `.planning/plans/dst-manager/PLAN-DM-001-v0.2-stabilization-and-multi-dwg-parallel.md` |
| `PLAN-DM-002` | `proposed` | `2026-08-11` | `.planning/plans/dst-manager/PLAN-DM-002-v0.3-daily-editor.md` |
| `PLAN-DM-003` | `proposed` | `2026-08-11` | `.planning/plans/dst-manager/PLAN-DM-003-v0.4-solo-workflow.md` |
| `PLAN-DM-004` | `proposed` | `2026-08-11` | `.planning/plans/dst-manager/PLAN-DM-004-v1.0-windows-productization.md` |
| `PLAN-DM-005` | `completed` | `2026-08-12` | `.planning/plans/dst-manager/PLAN-DM-005-v0.2.1-runtime-logging-and-acsm-hotfix.md` |
| `RES-SH-001` | `accepted` | `2026-08-11` | `docs/shared/research/project1-dst-xml/RES-SH-001-project1-dst-xml-analysis.md` |
| `RES-SH-002` | `accepted` | `2026-07-15` | `docs/shared/research/RES-SH-002-utilityclass-dst-xml-analysis.md` |
| `GUIDE-SH-001` | `accepted` | `2026-07-15` | `docs/shared/guides/GUIDE-SH-001-autocad-plugin-development.md` |
| `RES-SH-003` | `accepted` | `2026-07-15` | `docs/shared/research/RES-SH-003-transform-matrix-analysis.md` |
| `RES-SH-004` | `accepted` | `2026-07-15` | `docs/shared/research/RES-SH-004-autocad-2025-plus-migration.md` |

## 接口与依赖

- `docs/README.md` 是所有长期文档的唯一顶层入口。
- `.planning/README.md` 是所有执行性资料的唯一顶层入口。
- `docs/<scope>/README.md` 只链接当前有效文档，不复制正文。
- `related` 元数据使用稳定 ID；Markdown 正文使用相对链接。
- Task 2、3、4 分别产生可供 Task 5 汇总的项目索引和稳定新路径。
- Task 5 负责更新 `README.md`、`AGENTS.md` 和当前文档引用，并执行全仓断链审计。

---

### Task 1: 建立治理入口和最小模板

**Files:**
- Create: `docs/README.md`
- Create: `docs/_templates/prd.md`
- Create: `docs/_templates/spec.md`
- Create: `docs/_templates/adr.md`
- Create: `docs/_templates/rfc.md`
- Create: `docs/_templates/guide.md`
- Create: `docs/integration/README.md`
- Create: `docs/integration/rfcs/README.md`
- Create: `.planning/README.md`
- Create: `.planning/_templates/roadmap.md`
- Create: `.planning/_templates/plan.md`
- Create: `.planning/_templates/memo.md`
- Create: `.planning/roadmaps/integration.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `ARCH-INT-001` 中的目录、类型、状态和归属规则。
- Produces: 后续迁移批次使用的模板、长期文档入口、执行资料入口和整合入口。

- [ ] **Step 1: 创建不会指向未来文件的顶层索引**

使用 `apply_patch` 创建索引。`docs/README.md` 首次只链接当前已存在的 `ARCH-INT-001`、现有根级文档和 `integration/README.md`；后续任务在移动文件的同一个提交中替换为项目入口。`.planning/README.md` 首次链接现有 `.planning/todos/README.md` 和 `roadmaps/integration.md`，不提前链接尚未创建的项目路线图。

`docs/integration/README.md` 固定包含：范围说明、当前有效架构 `ARCH-INT-001`、RFC 索引、整合路线图，以及“产品私有功能不得放入本目录”的边界。`docs/integration/rfcs/README.md` 明确当前没有处于 `review` 状态的 RFC，新提案从 `RFC-INT-001` 开始编号。

- [ ] **Step 2: 创建长期文档模板**

模板 front matter 使用以下完整字段；模板正文只保留各类型要求的固定章节，示例值用尖括号表达并在复制模板时替换：

```yaml
---
id: <TYPE-SCOPE-NNN>
title: <简体中文标题>
status: draft
owners:
  - <legacy-refactor|dst-manager|shared|integration>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
related: []
---
```

正文结构：

```text
prd.md: 背景 / 目标用户 / 问题 / 目标 / 非目标 / 需求 / 验收标准
spec.md: 背景 / 范围 / 行为 / 接口 / 数据 / 异常 / 安全边界 / 兼容性 / 测试
adr.md: 背景 / 决策 / 备选方案 / 影响 / 替代关系
rfc.md: 提案 / 动机 / 影响范围 / 迁移路径 / 开放问题 / 评审结论
guide.md: 适用范围 / 前置条件 / 操作步骤 / 验证 / 故障处理
```

- [ ] **Step 3: 创建计划模板和整合路线图**

`.planning/_templates/roadmap.md` 使用 `proposed` 状态，正文为“目标阶段 / 交付结果 / 依赖 / 退出条件”。`.planning/_templates/plan.md` 使用 `proposed` 状态，正文为“目标 / 前置条件 / 任务 / 验证 / 风险 / 完成标准”。`.planning/_templates/memo.md` 不分配 ID，使用“日期 / 背景 / 事实 / 临时结论 / 待跟进事项”。

`.planning/roadmaps/integration.md` 的正式内容为：当前阶段只完成文档治理和项目边界显式化；任何代码、领域模型或部署整合必须先有被接受的 `RFC-INT-*`；目前没有已批准的产品合并里程碑，也不设置虚构日期。

- [ ] **Step 4: 验证新增入口没有断链**

Run:

```powershell
rtk rg -n "ARCH-INT-001|integration|legacy-refactor|dst-manager|shared" docs/README.md docs/integration .planning/README.md .planning/roadmaps/integration.md
rtk git diff --check
```

Expected: 第一条命令显示四个范围及 `ARCH-INT-001` 的入口；第二条命令无输出并以 0 退出。

- [ ] **Step 5: 更新变更记录并提交**

在 `changelog.md` 当前日期章节追加“建立文档治理入口、模板和整合路线图；尚未移动业务文档”。然后执行：

```powershell
rtk git add -- docs/README.md docs/_templates docs/integration/README.md docs/integration/rfcs/README.md .planning/README.md .planning/_templates .planning/roadmaps/integration.md changelog.md
rtk git diff --cached --check
rtk git commit -m "建立文档治理入口与模板"
```

Expected: 提交成功，未包含现有业务文档移动。

---

### Task 2: 迁移 Legacy Python 重构文档

**Files:**
- Create: `docs/legacy-refactor/README.md`
- Create: `docs/legacy-refactor/product/vision.md`
- Create: `.planning/roadmaps/legacy-refactor.md`
- Move: `docs/MODERN_PYTHON_REFACTOR_ARCHITECTURE.md` → `docs/legacy-refactor/architecture/ARCH-LR-001-modern-python-refactor-baseline.md`
- Move: `docs/PYTHON_REFACTOR_ASSESSMENT.md` → `docs/legacy-refactor/research/RES-LR-001-python-refactor-assessment.md`
- Move: `docs/DEVELOPMENT.md` → `docs/legacy-refactor/guides/GUIDE-LR-001-legacy-development-handover.md`
- Modify: `docs/legacy-refactor/research/RES-LR-001-python-refactor-assessment.md`
- Modify: `docs/legacy-refactor/guides/GUIDE-LR-001-legacy-development-handover.md`
- Modify: `docs/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 1 的索引和模板规则。
- Produces: Legacy 产品入口、Vision、Roadmap 和三个稳定文档路径。

- [ ] **Step 1: 创建目标目录并保留历史移动文件**

```powershell
rtk proxy powershell -NoProfile -Command "New-Item -ItemType Directory -Force 'docs/legacy-refactor/architecture','docs/legacy-refactor/research','docs/legacy-refactor/guides','docs/legacy-refactor/product','.planning/roadmaps' | Out-Null"
rtk git mv docs/MODERN_PYTHON_REFACTOR_ARCHITECTURE.md docs/legacy-refactor/architecture/ARCH-LR-001-modern-python-refactor-baseline.md
rtk git mv docs/PYTHON_REFACTOR_ASSESSMENT.md docs/legacy-refactor/research/RES-LR-001-python-refactor-assessment.md
rtk git mv docs/DEVELOPMENT.md docs/legacy-refactor/guides/GUIDE-LR-001-legacy-development-handover.md
```

Expected: `git status --short` 显示三个 rename，不显示删除后重新创建。

- [ ] **Step 2: 增加正式元数据并修复内部链接**

使用“文件结构与职责”表中的 ID、状态和创建日期；三个文件的 `owners` 均为 `legacy-refactor`，`updated` 使用执行当天日期。`ARCH-LR-001` 额外增加：

```yaml
document_kind: architecture-baseline
```

Task 4 才移动共享插件文档。为保证 Task 2 的提交本身没有断链，Assessment 和 Legacy Guide 暂时把原 `PLUGIN_DEVELOPMENT.md` 链接改为 `../../PLUGIN_DEVELOPMENT.md`；从两个新目录解析后仍指向当前存在的 `docs/PLUGIN_DEVELOPMENT.md`。Task 4 在移动共享文档的同一提交中把这两个链接替换为 `../../shared/guides/GUIDE-SH-001-autocad-plugin-development.md`。

- [ ] **Step 3: 创建 Legacy Vision、Roadmap 和索引**

`vision.md` 明确：以现代 Python 重构现有生成工具编排层；Python 负责业务编排、Web/API、Excel、任务、存储和审计；必须在 AutoCAD 内运行的能力保留 C#；目标覆盖从输入到 DWG、DST 和伴随成果的生成工作流；不把 `pyautocad` 作为全系统基础。

`.planning/roadmaps/legacy-refactor.md` 从 `ARCH-LR-001` 的迁移阶段提取六个阶段：黄金样本、纯逻辑、Core Console 调度、界面与打包、DST 迁移、pyautocad POC。状态写为 `proposed`，不声称尚未验证的阶段已经完成。

`docs/legacy-refactor/README.md` 链接 Vision、Roadmap、`ARCH-LR-001`、`RES-LR-001` 和 `GUIDE-LR-001`，并声明当前没有独立 PRD/Spec，后续需求按模板新增，不从基线批量复制。

- [ ] **Step 4: 更新顶层索引并验证本批次**

把 `docs/README.md` 的 Legacy 入口改为 `legacy-refactor/README.md`，移除对三个旧根路径的链接。

Run:

```powershell
rtk rg -n "ARCH-LR-001|RES-LR-001|GUIDE-LR-001" docs/legacy-refactor .planning/roadmaps/legacy-refactor.md docs/README.md
rtk proxy powershell -NoProfile -Command "'docs/MODERN_PYTHON_REFACTOR_ARCHITECTURE.md','docs/PYTHON_REFACTOR_ASSESSMENT.md','docs/DEVELOPMENT.md' | ForEach-Object { if (Test-Path -LiteralPath $_) { throw ('旧路径仍存在: ' + $_) } }"
rtk git diff --check
```

Expected: ID 均可从索引定位；三个旧路径不存在；差异检查无输出。

- [ ] **Step 5: 更新变更记录并提交**

```powershell
rtk git add -- docs/legacy-refactor .planning/roadmaps/legacy-refactor.md docs/README.md changelog.md
rtk git diff --cached --check
rtk git commit -m "归档 Legacy 重构文档体系"
```

Expected: 提交只包含 Legacy 文档、相应索引、路线图和变更记录。

---

### Task 3: 迁移 DST Manager 文档与阶段计划

**Files:**
- Create: `docs/dst-manager/README.md`
- Create: `docs/dst-manager/product/vision.md`
- Create: `.planning/roadmaps/dst-manager.md`
- Move: `docs/DST_MANAGER_MVP_DESIGN.md` → `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md`
- Move: `.planning/todos/01-v0.2-stabilization-and-multi-dwg-parallel.md` → `.planning/plans/dst-manager/PLAN-DM-001-v0.2-stabilization-and-multi-dwg-parallel.md`
- Move: `.planning/todos/02-v0.3-daily-editor.md` → `.planning/plans/dst-manager/PLAN-DM-002-v0.3-daily-editor.md`
- Move: `.planning/todos/03-v0.4-solo-workflow.md` → `.planning/plans/dst-manager/PLAN-DM-003-v0.4-solo-workflow.md`
- Move: `.planning/todos/04-v1.0-windows-productization.md` → `.planning/plans/dst-manager/PLAN-DM-004-v1.0-windows-productization.md`
- Move: `.planning/todos/05-v0.2.1-runtime-logging-and-acsm-hotfix.md` → `.planning/plans/dst-manager/PLAN-DM-005-v0.2.1-runtime-logging-and-acsm-hotfix.md`
- Replace: `.planning/todos/README.md` → `.planning/plans/dst-manager/README.md`
- Modify: `docs/README.md`
- Modify: `.planning/README.md`
- Modify: `AGENTS.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 1 的状态和计划模板。
- Produces: DST Manager 的产品入口、架构基线、Roadmap、五份正式 Plan 和更新后的代理必读路径。

- [ ] **Step 1: 移动架构基线和五份计划**

创建 `docs/dst-manager/architecture`、`docs/dst-manager/product` 和 `.planning/plans/dst-manager`，再使用 `git mv` 按 Files 清单逐一移动。把原 `.planning/todos/README.md` 移动为 `.planning/plans/dst-manager/README.md`，随后使用 `apply_patch` 修正其中五个新文件名链接。

- [ ] **Step 2: 增加架构和计划元数据**

`ARCH-DM-001` 使用表中元数据，`owners: [dst-manager]`，额外增加 `document_kind: architecture-baseline`。

五份 Plan 使用表中 ID、状态和创建日期，`owners: [dst-manager]`，`related` 至少包含 `ARCH-DM-001`。`PLAN-DM-001` 和 `PLAN-DM-005` 已由当前版本和勾选项证明完成，标记 `completed`；其余三份保持 `proposed`。不要把未勾选任务机械改成已完成；在完成计划末尾增加“实际验证摘要”，只引用现有 `changelog.md` 已记录的 v0.2/v0.2.1 验证事实。

- [ ] **Step 3: 创建 DST Manager Vision、Roadmap 和索引**

`vision.md` 明确：为单人单机真实工程提供可审计、可恢复的 DST/DWG 检查、编辑和发布工具；写入必须经过预览、基准修订、CAD Worker、验证和整批发布；MVP 只监听 `127.0.0.1`。

`.planning/roadmaps/dst-manager.md` 以 v0.2.1、v0.3、v0.4、v1.0 为阶段，链接五份 Plan；v0.2 和 v0.2.1 标为已完成，未来阶段保持计划状态。`docs/dst-manager/README.md` 链接 Vision、Roadmap、`ARCH-DM-001` 和当前 Plan 索引。

- [ ] **Step 4: 更新代理指令和顶层索引**

把 `AGENTS.md` 的必读路径从 `docs/DST_MANAGER_MVP_DESIGN.md` 改为 `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md`。把文档归档约定更新为本设计的 `docs/<scope>/...`、`.planning/roadmaps/`、`.planning/plans/`、`.planning/todos/` 和 `.planning/memos/`，并明确 Todo 只保存尚未形成 Plan 的事项。

同步更新 `docs/README.md` 和 `.planning/README.md`，使 DST Manager 分别指向新产品入口和 Roadmap/Plan 索引。

- [ ] **Step 5: 验证 DST Manager 迁移**

```powershell
rtk rg -n "ARCH-DM-001|PLAN-DM-00[1-5]" docs/dst-manager .planning/plans/dst-manager .planning/roadmaps/dst-manager.md AGENTS.md
rtk proxy powershell -NoProfile -Command "'docs/DST_MANAGER_MVP_DESIGN.md','.planning/todos/01-v0.2-stabilization-and-multi-dwg-parallel.md','.planning/todos/02-v0.3-daily-editor.md','.planning/todos/03-v0.4-solo-workflow.md','.planning/todos/04-v1.0-windows-productization.md','.planning/todos/05-v0.2.1-runtime-logging-and-acsm-hotfix.md' | ForEach-Object { if (Test-Path -LiteralPath $_) { throw ('旧路径仍存在: ' + $_) } }"
rtk git diff --check
```

Expected: 新 ID 均可定位；六个旧文件路径不存在；差异检查无输出。

- [ ] **Step 6: 更新变更记录并提交**

```powershell
rtk git add -- docs/dst-manager .planning/plans/dst-manager .planning/roadmaps/dst-manager.md docs/README.md .planning/README.md AGENTS.md changelog.md
rtk git diff --cached --check
rtk git commit -m "整理 DST Manager 文档与计划"
```

Expected: 提交只包含 DST Manager 文档、计划、索引、代理指令和变更记录。

---

### Task 4: 迁移公共技术资料与研究证据

**Files:**
- Create: `docs/shared/README.md`
- Move: `docs/PROJECT1_DST_XML_ANALYSIS.md` → `docs/shared/research/project1-dst-xml/RES-SH-001-project1-dst-xml-analysis.md`
- Move: `docs/project1_sheetset.xml` → `docs/shared/research/project1-dst-xml/project1_sheetset.xml`
- Move: `docs/project1_sheet_manifest.csv` → `docs/shared/research/project1-dst-xml/project1_sheet_manifest.csv`
- Move: `docs/UTILITYCLASS_DST_XML_ANALYSIS.md` → `docs/shared/research/RES-SH-002-utilityclass-dst-xml-analysis.md`
- Move: `docs/PLUGIN_DEVELOPMENT.md` → `docs/shared/guides/GUIDE-SH-001-autocad-plugin-development.md`
- Move: `docs/TRANSFORM_MATRIX_ANALYSIS.md` → `docs/shared/research/RES-SH-003-transform-matrix-analysis.md`
- Move: `docs/AUTOCAD_2025_PLUS_MIGRATION_ANALYSIS.md` → `docs/shared/research/RES-SH-004-autocad-2025-plus-migration.md`
- Modify: `docs/legacy-refactor/research/RES-LR-001-python-refactor-assessment.md`
- Modify: `docs/legacy-refactor/guides/GUIDE-LR-001-legacy-development-handover.md`
- Modify: `docs/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 2 中继续指向 `docs/PLUGIN_DEVELOPMENT.md` 的两个有效过渡链接。
- Produces: 公共技术资料入口、五个稳定文档 ID 和与样本研究共置的 XML/CSV 证据。

- [ ] **Step 1: 使用 `git mv` 移动公共文档和证据**

先创建 `docs/shared/guides`、`docs/shared/research` 和 `docs/shared/research/project1-dst-xml`，再严格按 Files 清单移动。XML 和 CSV 必须与 `RES-SH-001` 位于同一目录，不复制、不重新生成、不改变内容哈希。

- [ ] **Step 2: 增加元数据并修复相对链接**

五份 Markdown 使用表中 ID、状态和创建日期，`owners: [shared]`，`updated` 使用执行当天日期。`RES-SH-001` 正文中的输出清单文件名保持同目录相对引用。`RES-LR-001` 和 `GUIDE-LR-001` 指向 `GUIDE-SH-001` 的链接应在新位置解析成功。

`RES-SH-004` 中原来同目录的 `PLUGIN_DEVELOPMENT.md` 链接改为 `../guides/GUIDE-SH-001-autocad-plugin-development.md`；`RES-LR-001` 的链接保持 `../../shared/guides/GUIDE-SH-001-autocad-plugin-development.md`。

- [ ] **Step 3: 创建共享能力索引并更新顶层索引**

`docs/shared/README.md` 按“DST/AcSm”“AutoCAD 插件”“版本兼容”三个主题链接五份文档，并明确这些是两条产品线共同使用的技术知识，不是第三个产品。`docs/README.md` 的共享入口只链接 `shared/README.md`，不再平铺五个文件。

- [ ] **Step 4: 验证证据未变化和新链接可定位**

使用迁移前已经核验的 SHA-256 基线检查移动后的工作树文件：

```powershell
rtk certutil -hashfile docs/shared/research/project1-dst-xml/project1_sheetset.xml SHA256
rtk certutil -hashfile docs/shared/research/project1-dst-xml/project1_sheet_manifest.csv SHA256
rtk rg -n "RES-SH-00[1-4]|GUIDE-SH-001" docs/shared docs/legacy-refactor docs/README.md
rtk git diff --check
```

Expected: XML 哈希为 `36e4963ca954f67e7e01768b69aef75bc8af89478bc7d8816e9d2700dec4cd10`，CSV 哈希为 `0495a8e600175109b746aa0ccc151092675a5b1a3bea0da56a8dcf93a303fe86`；所有共享 ID 均可从索引定位；差异检查无输出。

- [ ] **Step 5: 更新变更记录并提交**

```powershell
rtk git add -- docs/shared docs/legacy-refactor/research/RES-LR-001-python-refactor-assessment.md docs/legacy-refactor/guides/GUIDE-LR-001-legacy-development-handover.md docs/README.md changelog.md
rtk git diff --cached --check
rtk git commit -m "归档公共 AutoCAD 与 DST 技术资料"
```

Expected: 提交包含公共文档与证据 rename、两处跨文档链接、索引和变更记录。

---

### Task 5: 收口仓库入口并执行全仓文档审计

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `.planning/README.md`
- Modify: `docs/integration/architecture/ARCH-INT-001-documentation-organization.md`
- Modify: `.planning/plans/integration/PLAN-INT-001-documentation-migration.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 2、3、4 产生的所有稳定新路径和索引。
- Produces: 无断链的仓库入口、已完成的迁移记录和可复核的最终状态。

- [ ] **Step 1: 简化根 README 的文档导航**

保留现有启动和排障说明。把“本地保留资料”之后平铺的多个文档链接收敛为：

- `docs/README.md`：完整文档入口；
- `docs/legacy-refactor/README.md`：Legacy Python 重构；
- `docs/dst-manager/README.md`：DST Manager；
- `docs/shared/README.md`：公共 AutoCAD/DST 能力；
- `docs/integration/README.md`：跨项目整合。

“主要入口”中的 DST Manager 设计链接改为 `ARCH-DM-001` 新路径。不要改动历史 `changelog.md` 条目中的旧路径。

- [ ] **Step 2: 记录迁移完成状态**

在 `ARCH-INT-001` 的迁移阶段后增加“实施状态”小节，记录 Task 1 至 Task 4 对应提交哈希和完成日期，不改写原始设计决策。在本计划 front matter 中把 `status` 改为 `completed`，并在末尾记录实际执行的验证命令及结果摘要。

在 `changelog.md` 当前日期章节追加最终迁移结果：两条产品线、共享能力和整合入口已经建立，旧平铺文档已通过 `git mv` 归档到新位置，样本证据哈希保持一致。

- [ ] **Step 3: 检查根级文档不再平铺**

```powershell
rtk proxy powershell -NoProfile -Command "$allowed = @('README.md'); $unexpected = Get-ChildItem -LiteralPath 'docs' -File -Filter '*.md' | Where-Object { $_.Name -notin $allowed }; if ($unexpected) { $unexpected.FullName; throw 'docs 根目录仍有未归类 Markdown' }"
rtk rg --files docs .planning
```

Expected: 第一条命令无输出；第二条命令显示所有 Markdown 均位于明确范围或模板目录。

- [ ] **Step 4: 检查当前文档不存在旧路径引用**

历史变更记录和迁移映射允许保留旧路径，因此从检查中排除 `changelog.md` 与 `ARCH-INT-001`：

```powershell
rtk rg -n "docs/(MODERN_PYTHON_REFACTOR_ARCHITECTURE|PYTHON_REFACTOR_ASSESSMENT|DEVELOPMENT|DST_MANAGER_MVP_DESIGN|PROJECT1_DST_XML_ANALYSIS|UTILITYCLASS_DST_XML_ANALYSIS|PLUGIN_DEVELOPMENT|TRANSFORM_MATRIX_ANALYSIS|AUTOCAD_2025_PLUS_MIGRATION_ANALYSIS)\.md|\.planning/todos/(01-v0\.2|02-v0\.3|03-v0\.4|04-v1\.0|05-v0\.2\.1)" README.md AGENTS.md docs .planning -g "!docs/integration/architecture/ARCH-INT-001-documentation-organization.md" -g "!PLAN-INT-001-documentation-migration.md"
```

Expected: 无输出。若发现引用，必须改为对应新路径后重新执行。

- [ ] **Step 5: 运行本地 Markdown 链接检查**

在 PowerShell 中执行以下只读检查；它忽略外部 URL、邮件地址和页内锚点，只验证仓库内相对文件链接：

```powershell
rtk proxy powershell -NoProfile -Command @'
$root = (Resolve-Path '.').Path
$files = Get-ChildItem -Path 'README.md','AGENTS.md','docs','.planning' -Recurse -File -Filter '*.md'
$broken = [System.Collections.Generic.List[string]]::new()
foreach ($file in $files) {
    $text = Get-Content -Raw -Encoding UTF8 -LiteralPath $file.FullName
    foreach ($match in [regex]::Matches($text, '\[[^\]]+\]\(([^)]+)\)')) {
        $target = $match.Groups[1].Value.Trim('<','>')
        if ($target -match '^(https?://|mailto:|#)') { continue }
        $pathPart = ($target -split '#', 2)[0]
        if ([string]::IsNullOrWhiteSpace($pathPart)) { continue }
        $resolved = Join-Path $file.DirectoryName ([uri]::UnescapeDataString($pathPart))
        if (-not (Test-Path -LiteralPath $resolved)) {
            $broken.Add("$($file.FullName): $target")
        }
    }
}
if ($broken.Count -gt 0) {
    $broken
    throw "发现 $($broken.Count) 个失效本地 Markdown 链接"
}
'@
```

Expected: 无失效链接并以 0 退出。

- [ ] **Step 6: 运行最终差异和文档内容检查**

```powershell
rtk rg -n "T[B]D|T[O]DO|PLACE[H]OLDER|待[补]" docs .planning -g "*.md" -g "!docs/_templates/**" -g "!.planning/_templates/**"
rtk git diff --check
rtk git status --short
```

Expected: 第一条命令仅允许模板示例中明确要求复制时替换的尖括号字段，不允许正式文档出现占位符；第二条命令无输出；第三条命令只显示本任务计划内文件。

- [ ] **Step 7: 提交最终收口**

```powershell
rtk git add -- README.md docs/README.md .planning/README.md docs/integration/architecture/ARCH-INT-001-documentation-organization.md .planning/plans/integration/PLAN-INT-001-documentation-migration.md changelog.md
rtk git diff --cached --check
rtk git commit -m "完成双项目文档迁移与链接审计"
rtk git status --short
```

Expected: 提交成功；最终 `git status --short` 无输出。

---

## 最终验收

执行完全部任务后，逐项确认：

- [ ] `docs/README.md` 和 `.planning/README.md` 均能在三次点击内到达所有当前有效文档。
- [ ] Legacy Python 重构、DST Manager、共享能力和跨项目整合都有独立入口。
- [ ] 两份大型架构基线仅增加元数据和位置变化，正文决策未被重新解释。
- [ ] 五份 DST Manager 阶段文档均成为正式 Plan，完成状态与现有证据一致。
- [ ] Project1 XML/CSV 研究证据与正文共置，迁移前后 SHA-256 一致。
- [ ] `AGENTS.md` 的必读路径和归档约定与新结构一致。
- [ ] 当前文档不存在旧路径引用或失效本地链接。
- [ ] `docs/` 根目录不再平铺业务 Markdown。
- [ ] `legacy/`、`sample/`、源码、依赖锁和数据库均未修改。
- [ ] 每个迁移批次都有独立简体中文提交，最终工作区干净。

## 风险与控制

- Git 对大小写重命名在 Windows 上可能折叠：所有目标文件名同时改变目录和完整文件名，统一使用 `git mv`，每次移动后检查 `git status --short`。
- 跨批次链接可能短暂失效：Task 2 明确记录共享目标，Task 4 在提交前必须建立目标并运行链接检查；若要求每个中间提交都绝对无断链，则把 Task 2 的共享链接暂时保留旧路径，到 Task 4 同时修改。
- 历史变更记录包含旧路径：审计命令显式排除 `changelog.md`，避免错误改写历史事实。
- XML/CSV 证据可能被换行转换：使用 `git mv` 且不经过文本编辑，移动前后比较 SHA-256。
- 空目录不会被 Git 保存：只在目录拥有首个实际文件时创建，不提交 `.gitkeep`。
