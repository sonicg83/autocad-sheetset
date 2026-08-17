---
id: ARCH-INT-001
title: 双项目文档组织与治理设计
status: accepted
document_kind: architecture
owners:
  - legacy-refactor
  - dst-manager
created: 2026-08-17
updated: 2026-08-17
related: []
---

# 双项目文档组织与治理设计

## 1. 背景与目标

仓库目前并行推进两条产品线：

- `legacy-refactor`：把现有 Excel、PowerShell/WPF 和 AutoCAD 编排链路重构为现代 Python 应用；
- `dst-manager`：打开、检查、编辑并安全发布既有 DST/DWG 的管理工具。

两条产品线未来可能合并为一个产品的不同模块，也可能保持为两个产品并共享底层能力。当前不提前确定最终形态。文档结构需要同时满足以下目标：

- 清楚区分两条产品线的产品需求、功能规格、架构和实施计划；
- 为已经复用的能力提供稳定的公共知识入口；
- 为跨项目契约、整合提案和未来合并路线保留独立空间；
- 区分长期有效的事实与知识，以及有时效性的计划、待办和备忘；
- 通过少量固定文档类型、状态和索引降低维护成本；
- 允许现有大型设计基线渐进拆分，不因整理文档而改写历史含义。

本设计只规定文档组织与治理方式，不决定两个产品的代码合并、发布方式或最终产品形态。

## 2. 总体原则

采用“项目优先的混合结构”：

1. 每条产品线拥有完整、独立的产品和工程文档。
2. 只有已经被两边采用的能力才进入 `shared/`。
3. 尚在讨论的共享、契约和合并议题进入 `integration/`。
4. `docs/` 保存长期事实、规范和可复用知识。
5. `.planning/` 保存路线图、实施计划、待办和临时记录。
6. 文档按主要用途只保留一个权威位置，其他位置使用链接，不复制正文。
7. 当前大型设计文档先作为架构基线迁移，后续随真实需求渐进拆分。

## 3. 目标目录

```text
docs/
├─ README.md
├─ _templates/
│  ├─ prd.md
│  ├─ spec.md
│  ├─ adr.md
│  ├─ rfc.md
│  └─ guide.md
├─ legacy-refactor/
│  ├─ README.md
│  ├─ product/
│  │  ├─ vision.md
│  │  └─ prds/
│  ├─ specs/
│  ├─ architecture/
│  ├─ adr/
│  ├─ guides/
│  └─ research/
├─ dst-manager/
│  ├─ README.md
│  ├─ product/
│  │  ├─ vision.md
│  │  └─ prds/
│  ├─ specs/
│  ├─ architecture/
│  ├─ adr/
│  ├─ guides/
│  └─ research/
├─ shared/
│  ├─ README.md
│  ├─ architecture/
│  ├─ adr/
│  ├─ guides/
│  ├─ reference/
│  └─ research/
├─ integration/
│  ├─ README.md
│  ├─ rfcs/
│  ├─ architecture/
│  └─ adr/
└─ archive/
   ├─ legacy-refactor/
   ├─ dst-manager/
   ├─ shared/
   └─ integration/

.planning/
├─ README.md
├─ _templates/
│  ├─ roadmap.md
│  ├─ plan.md
│  └─ memo.md
├─ roadmaps/
│  ├─ legacy-refactor.md
│  ├─ dst-manager.md
│  └─ integration.md
├─ plans/
│  ├─ legacy-refactor/
│  ├─ dst-manager/
│  ├─ shared/
│  └─ integration/
├─ todos/
│  ├─ legacy-refactor/
│  ├─ dst-manager/
│  ├─ shared/
│  └─ integration/
└─ memos/
   ├─ legacy-refactor/
   ├─ dst-manager/
   ├─ shared/
   └─ integration/
```

## 4. 归属边界

### 4.1 产品线

`legacy-refactor/` 负责从 Excel 或其他项目输入生成 DWG、DST 和伴随成果的生成型工作流。

`dst-manager/` 负责打开、诊断、编辑、修订和安全发布既有 DST/DWG 的管理型工作流。

两条产品线分别维护自己的 Vision、PRD、Spec、架构、ADR、指南和调研。只服务一条产品线的文档不得因为“未来可能复用”提前放入公共目录。

### 4.2 公共能力

`shared/` 只保存已经被两条产品线采用的公共能力，包括稳定架构、接口契约、操作指南、参考资料和技术研究。典型主题包括：

- DST Codec 与 AcSm DOM；
- AutoCAD Worker 与插件；
- Core Console 执行边界；
- 命名和布局规则中已经统一的部分；
- AutoCAD 版本兼容与插件构建。

公共层不是第三个产品，因此不设置 `product/`。某个共享能力的用户价值和功能需求仍应归属首先提出需求的产品；公共目录记录两边共同依赖的稳定技术契约。

### 4.3 跨项目整合

`integration/` 保存尚未落定的跨项目 RFC、整合架构、已确认的整合 ADR，以及两个项目之间的稳定边界。典型主题包括：

- 统一领域模型的提案；
- 共享 Worker 或任务协议；
- 两条产品线的模块拆分与依赖方向；
- 合并或保持独立部署的演进路线；
- 从项目私有能力提取公共模块的迁移方案。

它不保存某一产品自身的功能设计，也不作为公共实现文档的永久位置。RFC 通过后，应把稳定结论写入对应的 Spec、Architecture 或 ADR。

### 4.4 归档

`archive/` 只保存已经失效、仍具有独立追溯价值且不能仅依靠 Git 历史理解的文档。被新文档取代的正式规范应保留原编号并标记 `superseded`，必要时再移入归档目录。无长期价值的临时材料由 Git 历史保留，不要求全部归档。

## 5. 文档类型

| 类型 | 核心问题 | 位置 | 生命周期 |
| --- | --- | --- | --- |
| Vision | 产品最终解决什么问题 | `<project>/product/vision.md` | 长期 |
| PRD | 用户需要什么，范围和验收标准是什么 | `<project>/product/prds/` | 长期 |
| Spec | 功能或技术能力具体如何工作 | `<project>/specs/` | 长期 |
| Architecture | 当前系统结构和模块边界是什么 | `<scope>/architecture/` | 长期 |
| ADR | 为什么选择某个关键技术决策 | `<scope>/adr/` | 长期、不可覆写结论 |
| RFC | 跨项目或高影响提案是什么 | `integration/rfcs/` | 评审期间有效 |
| Roadmap | 各阶段准备交付什么 | `.planning/roadmaps/` | 有时效性 |
| Plan | 一次具体实施如何分步完成 | `.planning/plans/` | 执行期间有效 |
| Todo | 尚未展开成正式计划的任务是什么 | `.planning/todos/` | 临时 |
| Memo | 临时讨论、排查和阶段结论是什么 | `.planning/memos/` | 临时 |
| Guide | 如何完成安装、开发、测试或发布 | `<scope>/guides/` | 长期 |
| Reference | 稳定字段、协议和命令是什么 | `shared/reference/` | 长期 |
| Research | 调研、实验或逆向分析得到什么 | `<scope>/research/` | 通常长期 |

### 5.1 文档链路

单项目功能遵循：

```text
Vision
  → PRD：定义问题、范围与验收
  → Spec：定义行为、接口、数据和异常
  → ADR：记录关键方案取舍
  → Plan：拆解本次实施与验证
  → 代码、测试和发布
```

跨项目能力遵循：

```text
RFC
  → 评审通过
  → 共享 Spec、Architecture 或 ADR
  → 两个项目各自的实施 Plan
```

### 5.2 类型边界

- PRD 不描述类名、数据库表或逐文件实现步骤。
- Spec 可以定义 API、状态机、数据结构、异常、安全边界、兼容性和验收测试，但不承担施工清单职责。
- Architecture 描述当前有效结构；未采纳的架构设想进入 RFC 或 Research。
- ADR 一份只记录一个关键决策。结论变化时新增 ADR，并把旧 ADR 标记为 `superseded`。
- Plan 必须具有明确完成条件；完成后记录实际验证，不继续演变为永久架构文档。
- Research 可以提出建议，但建议只有进入 Spec、Architecture 或 ADR 后才成为当前规范。

## 6. 编号、命名与元数据

### 6.1 范围代码

| 范围 | 代码 |
| --- | --- |
| Legacy Python 重构 | `LR` |
| DST Manager | `DM` |
| 公共能力 | `SH` |
| 跨项目整合 | `INT` |

正式文档使用“文档类型 + 范围代码 + 三位序号”作为永久 ID，例如：

```text
PRD-LR-001
SPEC-DM-003
ADR-SH-002
RFC-INT-001
PLAN-LR-004
```

文件名使用 ID 加英文短名称：

```text
PRD-LR-001-sheetset-generation.md
SPEC-DM-003-safe-publish.md
ADR-SH-002-dst-codec-ownership.md
RFC-INT-001-domain-model-integration.md
PLAN-LR-004-excel-import.md
```

正文标题、内容、注释和提交信息继续使用简体中文。Memo 使用 `YYYY-MM-DD-topic.md`，不分配永久编号。Guide、Reference 和 Research 仅在需要稳定交叉引用时编号。

编号永久保留，不因移动、改名、作废或归档而重用。

### 6.2 元数据

PRD、Spec、Architecture、ADR、RFC、Roadmap 和 Plan 必须包含 YAML 元数据。Guide、Reference、Research 和 Memo 可按需要使用。

```yaml
---
id: SPEC-DM-003
title: DST 安全发布规范
status: accepted
owners:
  - dst-manager
created: 2026-08-17
updated: 2026-08-17
related:
  - PRD-DM-002
  - ADR-SH-002
---
```

`related` 使用文档 ID，不写容易因移动失效的相对路径。实际 Markdown 正文仍应提供可点击链接。

### 6.3 状态

长期文档使用：

```text
draft → review → accepted → superseded
                         ↘ archived
```

计划类文档使用：

```text
proposed → active → completed
                  ↘ cancelled
                  ↘ blocked
```

`blocked` 必须记录阻断原因和恢复条件。`completed` 必须记录实际执行的验证。状态只描述文档或计划本身，不替代代码版本和发布状态。

## 7. 索引与导航

每个层级的 `README.md` 是导航索引，不复制下级文档正文。

根 `docs/README.md` 至少链接：

- 两条产品线入口；
- 公共能力入口；
- 跨项目整合入口；
- 当前有效的文档规范和模板；
- 已归档文档入口。

每个产品线的 `README.md` 至少说明：

- 产品定位和当前版本；
- Vision 和当前 Roadmap；
- 当前有效的 PRD、Spec 和 Architecture；
- 已接受 ADR；
- 开发、测试、部署和使用指南。

`shared/README.md` 按能力域组织链接，`integration/README.md` 列出正在评审的 RFC、已接受整合决策和整合路线。

仓库根 `README.md` 只承担仓库简介、快速启动和文档入口，不继续累积完整架构、调研和交接内容。

## 8. 模板的最小内容

模板只规定必要内容，不引入复杂文档生成器。

- PRD：背景、目标用户、问题、目标、非目标、需求、验收标准。
- Spec：背景、范围、行为、接口、数据、异常、安全边界、兼容性、测试。
- ADR：背景、决策、备选方案、影响、替代关系。
- RFC：提案、动机、影响范围、迁移路径、开放问题、评审结论。
- Guide：适用范围、前置条件、步骤、验证、故障处理。
- Roadmap：目标阶段、交付结果、依赖、退出条件。
- Plan：目标、前置条件、任务、验证、风险、完成标准。
- Memo：日期、参与背景、事实、临时结论、待跟进事项。

## 9. 现有文档迁移映射

首轮迁移不拆改大型设计正文，只改变位置、增加元数据和修复链接。

| 现有文档 | 目标位置 | 处理方式 |
| --- | --- | --- |
| `docs/MODERN_PYTHON_REFACTOR_ARCHITECTURE.md` | `docs/legacy-refactor/architecture/` | 作为 `architecture-baseline` 迁移，后续渐进拆分 PRD、Spec 和 ADR |
| `docs/PYTHON_REFACTOR_ASSESSMENT.md` | `docs/legacy-refactor/research/` | 原样迁移为重构可行性调研 |
| `docs/DEVELOPMENT.md` | `docs/legacy-refactor/guides/` | 改名为旧生成工具开发与交接指南 |
| `docs/DST_MANAGER_MVP_DESIGN.md` | `docs/dst-manager/architecture/` | 作为 `architecture-baseline` 迁移，后续渐进拆分 |
| `.planning/todos/01` 至 `05` | `.planning/plans/dst-manager/` | 阶段文档归为 Plan，按实际状态补元数据 |
| `docs/PROJECT1_DST_XML_ANALYSIS.md` | `docs/shared/research/` | 迁移为 DST/AcSm 样本研究 |
| `docs/UTILITYCLASS_DST_XML_ANALYSIS.md` | `docs/shared/research/` | 迁移为 DST Codec 逆向与兼容性研究 |
| `docs/PLUGIN_DEVELOPMENT.md` | `docs/shared/guides/` | 迁移为两条产品线共用的插件指南 |
| `docs/TRANSFORM_MATRIX_ANALYSIS.md` | `docs/shared/research/` | 迁移为公共插件技术研究 |
| `docs/AUTOCAD_2025_PLUS_MIGRATION_ANALYSIS.md` | `docs/shared/research/` | 迁移为公共 CAD 运行时研究 |

与 `PROJECT1_DST_XML_ANALYSIS.md` 配套的 XML 和 CSV 证据文件应随研究文档迁移到同一主题子目录，避免研究正文和证据分离。

两份大型设计基线迁移后使用：

```yaml
status: accepted
document_kind: architecture-baseline
```

它们继续作为有效历史依据，但不再追加所有新需求、计划和决策。

## 10. 迁移阶段

### 阶段 1：建立骨架和入口

- 创建目标目录、模板和各级 `README.md`；
- 创建两条产品线的 Vision；
- 创建三份 Roadmap 入口；
- 移动现有文档并修复仓库内链接；
- 保持文档正文语义不变。

### 阶段 2：补充元数据和状态

- 为正式文档分配 ID；
- 标记当前有效、已完成和已失效文档；
- 把现有 DST Manager 阶段文档从 Todo 归类为 Plan；
- 给已完成计划补充实际验证摘要。

### 阶段 3：按需渐进拆分

- 新需求出现时创建独立 PRD 和 Spec；
- 从大型设计基线提取仍有效的关键 ADR；
- 对重复或冲突规则明确唯一权威文档；
- 通过 RFC 处理真正的跨项目共享和整合，不为追求形式一次性生成大量文档。

## 11. 日常治理规则

新增文档时依次判断：

1. 它是长期事实或规范，还是有时效性的执行材料；
2. 它只服务某一产品、已被两边采用，还是正在讨论跨项目整合；
3. 它回答的是产品目标、功能行为、架构、决策、操作方法、参考信息还是研究结论；
4. 是否已经存在同主题权威文档，可以更新或链接而不是复制。

维护要求：

- PRD 或 Spec 变更时检查相关 Plan、测试和用户指南；
- 重大技术取舍新增 ADR，不静默覆盖旧决策；
- RFC 评审结束后记录结论，并将稳定内容写入正式规范；
- Plan 完成后记录实际验证，再标记 `completed`；
- `README.md` 只链接当前有效文档，历史内容通过状态和归档索引追踪；
- `changelog.md` 记录产品和仓库的可核验变化，不记录每次讨论过程；
- 每季度或重要版本发布前检查失效链接、孤立文档、过期状态、重复规范和未关闭 RFC。

## 12. 验收标准

完成文档迁移后应满足：

- 任一文档能从 `docs/README.md` 或 `.planning/README.md` 在三次以内点击到达；
- 两条产品线的当前 Vision、Roadmap、有效规范和开发指南均有明确入口；
- 根 `docs/` 不再平铺无法判断归属的业务 Markdown 文档；
- 每份正式文档都有唯一归属、稳定 ID、明确状态和必要关联；
- 同一规则不存在两份都声称权威但内容冲突的文档；
- 计划、待办和备忘不进入长期知识目录；
- Research 中的建议不会在未形成 Spec、Architecture 或 ADR 前被视为正式规范；
- 现有文档链接、README 导航和仓库内引用全部有效；
- 文档整理不改变应用行为，也不修改 `legacy/` 或 `sample/` 私有原件。

## 13. 明确不做

本轮文档治理不引入文档站点、数据库、专用知识库或自动发布流水线；不要求为所有 Markdown 编号；不一次性拆分现有大型设计基线；不提前决定两个产品最终合并方式；不把未被两边采用的代码或文档提前声明为共享能力。
