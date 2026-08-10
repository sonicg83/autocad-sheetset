# Python 与 pyautocad 重构可行性评估

> 分析日期：2026-07-15  
> 评估对象：AutoCAD 市政图纸集生成工具  
> 结论性质：架构决策建议，不包含本次代码实施

## 1. 执行摘要

本项目适合使用 Python 重构，但不建议把整个系统改造成以 `pyautocad` 为核心的实现。

推荐路线是：

> Python 负责 Excel、配置、输入校验、图纸业务模型、命名规则、任务调度、日志、界面和输出报告；保留 `accoreconsole.exe + AutoCAD .NET 插件` 作为 DWG 批处理引擎；DST 生成先复用现有能力，后续迁移到 Autodesk Sheet Set Object（SSO）COM API。

核心判断：

- “Python 化”收益较高，能明显改善可维护性、自动化测试、输入校验和错误处理。
- “pyautocad 化”收益有限。它是桌面 AutoCAD ActiveX/COM 的轻量封装，不能自然替代当前无界面、分批并行的 Core Console 处理方式。
- `pyautocad` 没有提供 Sheet Set Manager/DST 的高级封装，不能单独完成本项目的全部功能。
- 如果完全改用桌面 AutoCAD COM，批量处理吞吐量和无人值守稳定性可能低于现状。
- 最合理的实施方式是分层重构，而不是一次性重写。

## 2. 当前系统的关键能力

现有系统由以下部分组成：

1. WPF/PowerShell 界面选择 Excel 和模板。
2. EPPlus 读取 `SheetSet` 与 `Sheet` 工作表。
3. PowerShell 展开图纸分组、生成编号、布局名、图号和 DWG 文件名。
4. 根据模板类型、图幅和送审状态生成 AutoCAD `.scr` 文件。
5. `AcadScript` 分批启动多个 `accoreconsole.exe` 进程处理 DWG。
6. `AutoCad Utility.dll` 在 AutoCAD 内提供布局清理、布局句柄采集和签名参照插入等命令。
7. PowerShell 组装 Sheet Set XML，并通过 `UtilityClass.DstViewer.XmlToDst` 生成 `.dst`。
8. EPPlus 生成图纸目录，附带材料表和其他辅助成果。

现有关键调用位置：

- Core Console 调度：[`Functions.ps1`](../Functions.ps1) 中的 `AcadScript`。
- 正式批处理入口：[`图纸集生成-市政用0.24.ps1`](../图纸集生成-市政用0.24.ps1) 中 `$WPFConfirm.add_Click` 处理器。
- 布局句柄命令：生成的 AutoCAD 脚本中的 `GetLayoutHandles`。
- DST 输出：`[UtilityClass.DstViewer]::XmlToDst($xmldata, $dstfile)`。

当前架构最重要的特点不是 PowerShell，而是“业务编排器 + Core Console 批处理 + AutoCAD 内部插件”。重构时应保留这一有效分层。

## 3. pyautocad 的定位和维护状态

`pyautocad` 是对 AutoCAD ActiveX Automation/COM 的轻量封装，主要简化：

- 连接当前 AutoCAD 应用。
- 获取活动文档、模型空间和布局。
- 创建或遍历 AutoCAD 图元。
- 处理点坐标和常见 COM 类型转换。

其公开源码通过 `GetActiveObject('AutoCAD.Application')` 获取活动 AutoCAD，或通过 `CreateObject('AutoCAD.Application')` 创建一个桌面实例，随后默认操作 `ActiveDocument`。参考：[pyautocad API 源码](https://pyautocad.readthedocs.io/en/latest/_modules/pyautocad/api.html)。

需要关注的维护风险：

- PyPI 最新版本为 `0.2.0`，发布于 2015-12-21，项目状态为 Beta。
- PyPI 声明的 Python 分类器停留在 Python 2.7、3.3、3.4、3.5。
- GitHub 主分支最后一次提交为 2016-10-13。
- 它依赖 `comtypes`，源码包含对 Autodesk Shared 类型库固定目录和文件模式的假设。

来源：

- [pyautocad PyPI 项目页](https://pypi.org/project/pyautocad/)
- [pyautocad GitHub 提交记录](https://github.com/reclosedev/pyautocad/commits/master/)
- [pyautocad GitHub 仓库](https://github.com/reclosedev/pyautocad)

这并不等于 `pyautocad` 在现代 Python 中必然无法运行，但意味着项目团队必须自行验证 AutoCAD 2016、当前 Python、`comtypes` 和 32/64 位组合，并承担后续修补责任。

## 4. pyautocad 与当前执行模型的冲突

### 4.1 当前是 Core Console 后台批处理

项目按照 `session` 配置，把 DWG 分组后启动多个 `accoreconsole.exe`。每个进程打开一个 DWG、运行同名 `.scr`、保存并退出。

这个模式的优点是：

- 不要求操作桌面 AutoCAD 界面。
- 每个 DWG 有相对独立的进程状态。
- 可以并发处理多个 DWG。
- AutoCAD 命令序列与单个文件绑定，定位失败文件较直接。

Autodesk 也把 Core Console 描述为可在后台运行脚本、减少批处理时间的选择：[Autodesk ScriptPro/Core Console 说明](https://help.autodesk.com/view/ACDLT/2024/ENU/?contextId=HYT_Blog_May_2021_Scripts)。

### 4.2 pyautocad 控制桌面 AutoCAD COM

`pyautocad` 默认连接 COM Running Object Table 中的活动 `AutoCAD.Application`，然后操作活动文档。这会引入：

- 活动文档和当前命令状态管理。
- 多个 AutoCAD 版本/实例的选择问题。
- COM 单线程单元（STA）和消息泵要求。
- 命令发送与完成检测。
- AutoCAD 对话框或异常状态阻塞自动化。
- 多实例并发时对象路由和进程回收风险。

因此，用 `pyautocad` 全面替换 Core Console，不能假设获得同等的无界面和并发能力。

## 5. 功能逐项映射

| 当前功能 | pyautocad 能否直接覆盖 | 推荐实现 | 评价 |
| --- | --- | --- | --- |
| Excel 输入读取 | 否 | `openpyxl` | Python 迁移收益高 |
| 输入字段、序号、路径校验 | 否 | Pydantic + 纯 Python | 应优先迁移 |
| 图纸分组展开 | 否 | 纯 Python 领域模型 | 易测试、收益高 |
| 编号、布局名、文件名 | 否 | 纯 Python 函数 | 易建立单元测试 |
| WPF 界面 | 否 | PySide6、Tkinter 或 CLI | 与 AutoCAD 库解耦 |
| DWG 打开和保存 | 可以 | COM 或保留 Core Console | 批量场景优先 Core Console |
| 枚举布局 | 可以 | `doc.Layouts` / `iter_layouts` | 适合 POC |
| 新建、删除、重命名布局 | 基本可以 | ActiveX Layout API | 需验证 AutoCAD 2016 |
| 从 DWG/DWT 导入完整布局 | 覆盖不完整 | `-LAYOUT Template` 命令或 .NET API | `CopyFrom` 不等同于完整模板导入 |
| 获取布局句柄 | 可以 | COM `Layout.Handle` | 可替代 `GetLayoutHandles` 的一部分价值 |
| 插入外部参照 | 可以 | `AttachExternalReference` 或自有命令 | 先确认 `Ainsert` 的真实语义 |
| 插入/绑定电子签名 | 不确定 | 复用插件或重新实现 | 需要插件源代码/行为测试 |
| 多进程无界面批处理 | 不适合 | 保留 `accoreconsole.exe` | 全面 COM 化可能退化 |
| DST 创建与修改 | pyautocad 不提供 | SSO COM API 或暂时复用 `UtilityClass.dll` | 独立技术边界 |
| 图纸目录输出 | 否 | `openpyxl` | 可完全 Python 化 |
| Word/PDF 辅助函数 | 否 | `python-docx`、`pypdf` 等 | 主流程当前未使用，可后迁移 |

### 5.1 布局操作

AutoCAD ActiveX `Layout` 对象提供 `Delete`、`CopyFrom`、`Name`、`Handle`、打印设置等成员；新布局可以通过 `Layouts.Add` 创建。参考：[Autodesk Layout ActiveX API](https://help.autodesk.com/cloudhelp/2023/DEU/AutoCAD-ActiveX-Reference/files/GUID-EFC848F1-26BE-4EFA-BC0E-11F874D73842.htm)。

但是当前系统需要从外部模板 DWG 导入布局及其图形内容。Autodesk 的 `LAYOUT` 命令 `Template` 选项会把外部 DWT/DWG/DXF 中的布局和对象插入当前图形：[LAYOUT 命令说明](https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Core/files/GUID-BCE3AD90-9DE0-488C-9CA4-5FDB9401DCE0.htm)。

因此，纯 COM 的 `Layouts.Add + Layout.CopyFrom` 是否能完全等价替代当前 `-LAYOUT T` 必须用实际模板验证。较可能的结果是：仍需通过 COM `SendCommand` 执行 `-LAYOUT`，或者在 AutoCAD .NET 插件中实现确定性的布局导入。

### 5.2 外部参照/电子签名

ActiveX 提供 `AttachExternalReference`，可以从模型空间、图纸空间或块中附着外部 DWG。参考：[AttachExternalReference API](https://help.autodesk.com/cloudhelp/2024/DEU/AutoCAD-LT-ActiveX-Reference/files/GUID-28CB9C44-08E6-47EF-A982-8F505D8C68F6.htm)。

`AutoCad Utility.dll` 的源码现已确认：`Ainsert` 排除模型空间，在所有图纸布局的 `(0, 0, 0)` 插入同一个外部 DWG；外参名取文件名，不显式设置比例、旋转、图层，也不执行绑定、转块或字段处理。主脚本会在调用前把当前图层设为 `0`。

因此可以用 ActiveX `AttachExternalReference` 加“逐布局追加块参照”重现其目标语义，但仍需用多布局 DWG 对比现有实现，尤其验证同名外参定义、布局块集合和保存后的引用路径。源码级说明见 [AutoCAD 插件开发与交接文档](PLUGIN_DEVELOPMENT.md)。

## 6. DST/Sheet Set 是独立的重构边界

当前项目构建 XML 后，通过 `UtilityClass.dll` 转为 DST。`pyautocad` 的公开 API没有提供 Sheet Set Manager 对象封装。

Autodesk 官方 Sheet Set Object 模型是另一组 COM 对象，包括：

- `AcSmSheetSetMgr`
- `AcSmDatabase`
- `AcSmSheetSet`
- `AcSmSubset`
- `AcSmSheet`
- `AcSmAcDbLayoutReference`
- `AcSmCustomPropertyBag`

官方说明：

- `AcSmSheetSetMgr` 用于创建或打开 DST 数据库。
- 数据库包含图纸集、子集、图纸和属性层次。
- `AcSmSheet` 引用特定 DWG 中的特定布局，并包含文件名、布局名、Handle、图纸编号和标题等信息。

参考：[Sheet Set Manager 对象概览](https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-ActiveX-SSO/files/GUID-56F608AE-CEB3-471E-8A64-8C909B989F24.htm)。

Autodesk 还要求修改 `AcSmDatabase` 前锁定数据库，完成后解锁并提交；并明确提出 DST 文件应通过 Sheet Set Manager 对象修改，而不是直接修改文件内容。参考：

- [修改 Sheet Set 的规范](https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-ActiveX-SSO/files/GUID-6D7E2FAD-BA29-4123-B4DF-52F9EE6E6AA7.htm)
- [创建或打开 Sheet Set Database](https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-ActiveX-SSO/files/GUID-A72E5F7E-D18F-4171-8D30-58FEFCC76E03.htm)
- [添加 Sheet Set 自定义属性](https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-ActiveX-SSO/files/GUID-E83ACFC3-47C1-4828-8686-06E7390E2845.htm)

长期建议是使用 Python 的 `comtypes` 或 `pywin32` 直接调用安装目录中的 AcSmComponents 类型库。这个能力与 `pyautocad` 无直接关系。

## 7. 可预期收益

### 7.1 可维护性

当前测试和正式生成处理器存在约 500 行高度重复代码。Python 重构后可统一为：

```text
读取输入
  ↓
校验并生成领域模型
  ↓
展开具体图纸和布局
  ↓
生成 CadJob 列表
  ↓
AutoCADAdapter 执行
  ↓
验证布局与句柄
  ↓
SheetSetAdapter 生成 DST
  ↓
输出目录和报告
```

测试/正式模式只需要通过参数控制输出路径、处理范围和是否生成最终成果。

### 7.2 输入校验

Python 可以在启动 AutoCAD 前完成：

- 工作表与字段存在性检查。
- 数值类型和非空检查。
- 序号断号、冲突和重叠检查。
- `张数 > 0` 检查。
- 编号是否超出 `SerialDigit`。
- 模板文件、模板布局和基础 DWG 检查。
- 外部参照路径检查。
- 输出目录可写性检查。
- 全局人员属性与逐图人员属性的回退规则检查。

这会减少 AutoCAD 已运行数分钟后才发现输入问题的情况。

### 7.3 自动化测试

以下规则均可在不启动 AutoCAD 的情况下测试：

- 单张和多张图纸的展开。
- 封面/扉页的特殊序号。
- 同名图纸的中文分张后缀。
- 文件名、布局名和图号。
- 送审版封面布局选择。
- Sheet Set 数据模型和自定义属性。
- 输出目录备份策略。

只有布局导入、外参/签名、Handle 和实际 DST 打开需要 AutoCAD 集成测试。

### 7.4 日志和错误恢复

建议为每个 CAD 任务记录：

- 输入 DWG、模板、布局和输出路径。
- 生成的 `.scr` 路径或命令序列。
- Core Console PID、退出码和耗时。
- 标准输出与标准错误。
- 期望布局数与实际布局数。
- 期望 Handle 数与实际 Handle 数。
- 重试次数和最终状态。

任何关键任务失败时应停止生成最终 DST，避免产生能够打开但引用不完整的图纸集。

### 7.5 依赖和配置

Python 可使用：

- `openpyxl`：替换 EPPlus Excel 读写。
- Pydantic：输入与配置模型。
- TOML：替换当前扁平 INI 解析。
- `logging` 或结构化日志库：统一日志。
- `subprocess` + 并发队列：控制 Core Console。
- PySide6：替换 WPF 界面。
- pytest：单元测试和集成测试。

这会消除现有 `ReadIni` 忽略节、值不能安全包含 `=`、资源释放不一致等问题。

## 8. 可能没有收益或发生退化的部分

### 8.1 DWG 处理性能

耗时主要来自：

- 启动 AutoCAD/Core Console。
- 加载基础 DWG 和模板。
- 加载 .NET 插件。
- 导入布局。
- 插入/处理签名参照。
- 保存 DWG。

把 PowerShell 改为 Python不会显著缩短这些步骤。性能收益主要来自更合理的任务队列、失败重试和避免无效任务，而不是语言本身。

### 8.2 桌面 COM 的稳定性

如果全面使用 `pyautocad`：

- 可能只能稳定串行处理或使用少量实例。
- 需要处理 AutoCAD 窗口、活动文档和未完成命令。
- COM 异常可能使整个 AutoCAD 实例进入不可继续状态。
- 关闭文档和退出应用时容易留下后台进程。
- 自动弹出的对话框会阻塞无人值守运行。

所以不能假设 pyautocad 版本会比当前 Core Console 更稳定。

### 8.3 AutoCAD 版本兼容

Python 不会消除以下边界：

- 当前 `AutoCad Utility.dll` 依赖 AutoCAD 2016 的 `Acdbmgd 20.1`。
- AutoCAD ActiveX 类型库和 Sheet Set 类型库与安装版本相关。
- 模板布局、字段、字体和打印设置仍依赖 AutoCAD 环境。
- 升级 AutoCAD 后可能需要重新编译插件。

## 9. 方案比较

| 方案 | 功能覆盖 | 批处理能力 | 维护风险 | 迁移风险 | 建议 |
| --- | --- | --- | --- | --- | --- |
| 保持 PowerShell，仅修补缺陷 | 高 | 保持现状 | 高 | 低 | 只适合短期止血 |
| 全面改为 pyautocad | 约 50%～60% 直接覆盖 | 可能退化 | 高，依赖老旧 | 高 | 不推荐 |
| Python + pyautocad + 桌面 AutoCAD | 中等 | 更适合串行/小批量 | 中高 | 中高 | 适合交互式小工具 |
| Python + Core Console + 现有插件 | 90% 以上可 Python 化 | 保持现状 | 中 | 中 | 第一阶段最推荐 |
| Python + Core Console + 新 .NET 插件 | 高 | 高 | 中低 | 中高 | 长期最稳妥 |
| Python + SSO COM 生成 DST | 覆盖 DST | 不影响 DWG 批处理 | 中 | 中高 | 推荐分阶段实施 |

表中覆盖比例为基于当前代码功能的工程估算，不是库官方指标。

## 10. 推荐目标架构

```text
Python 应用
├─ UI
│  ├─ PySide6 桌面界面
│  └─ CLI（自动化和调试）
├─ Application
│  ├─ GenerateProjectUseCase
│  ├─ ValidateInputUseCase
│  └─ TestGenerationUseCase
├─ Domain
│  ├─ SheetSet
│  ├─ SheetGroup
│  ├─ ExpandedSheet
│  ├─ TemplateSelection
│  └─ CadJob
├─ Infrastructure
│  ├─ ExcelRepository
│  ├─ ConfigRepository
│  ├─ AutoCADAdapter
│  │  ├─ CoreConsoleAdapter（主实现）
│  │  └─ ComAdapter（可选/POC）
│  ├─ SheetSetAdapter
│  │  ├─ LegacyUtilityClassAdapter（过渡）
│  │  └─ SsoComAdapter（目标）
│  └─ OutputRepository
└─ Tests
   ├─ unit
   ├─ contract
   └─ autocad_integration
```

### 关键设计原则

- 领域层不得依赖 AutoCAD、Excel、COM 或 UI。
- `AutoCADAdapter` 和 `SheetSetAdapter` 必须有接口，便于保留旧实现并逐步替换。
- 每个 CAD 任务必须是可序列化的数据对象，方便重试和生成诊断报告。
- DST 只在全部必需 CAD 任务成功且布局/Handle 校验通过后生成。
- 测试和正式模式复用同一条主流程。

## 11. 推荐迁移阶段

### 阶段 0：建立黄金样本

准备并保存以下输入和完整输出：

1. 最小项目：图纸目录 + 1 张通用图。
2. 多布局项目。
3. 包含封面、扉页和送审封面的项目。
4. 包含同名图纸分组的项目。
5. 包含自定义基础 DWG 的项目。
6. 包含电子签名参照的项目。

记录 DWG 文件、布局列表、布局 Handle、DST 属性、图纸目录、日志、总耗时和失败情况。

粗略工作量：2～4 个工作日。

### 阶段 1：迁移纯逻辑

实现：

- Python 项目结构和依赖管理。
- Excel 与配置读取。
- Pydantic 数据模型。
- 输入验证。
- 图纸展开和全部命名规则。
- 图纸目录输出。
- 单元测试。

该阶段继续调用原 PowerShell/AutoCAD 链路或产生完全相同的任务数据，不改变 DWG 行为。

粗略工作量：1～2 周。

### 阶段 2：Python 接管 Core Console 调度

实现：

- `.scr` 生成器。
- Core Console 任务队列。
- 并发上限、超时、退出码、重试。
- 分任务日志和汇总报告。
- 失败时阻止生成最终 DST。

继续复用 `AutoCad Utility.dll`。

粗略工作量：1～2 周。

### 阶段 3：界面和打包

实现 PySide6 或简化界面，并保留 CLI。提供配置检查、输入预览、验证结果、任务进度、取消和日志入口。

粗略工作量：1～2 周。

### 阶段 4：DST 迁移

实现 `SsoComAdapter`：

- 创建并锁定 `AcSmDatabase`。
- 创建图纸集和子集。
- 添加图纸集/图纸自定义属性。
- 创建布局引用并写入 DWG、布局名和 Handle。
- 提交或回滚数据库。

与黄金样本逐项比较后，再移除 `UtilityClass.dll`。

粗略工作量：2～4 周。

### 阶段 5：决定是否使用 pyautocad

只选一个 DWG 做 POC，验证：

- 指定并连接正确 AutoCAD 2016 实例。
- 删除默认布局。
- 从模板导入完整布局。
- 重命名并设置当前布局。
- 读取布局 Handle。
- 插入签名参照。
- 保存、关闭并可靠释放 COM 对象。
- 连续运行 20～50 次无残留进程或状态串扰。

如果布局模板导入仍大量依赖 `SendCommand`，或者多文件连续运行出现活动文档、命令同步、弹窗或 COM 回收问题，应停止全面采用 pyautocad。

粗略工作量：2～4 个工作日。

## 12. 工作量与人员预估

在一名熟悉 Python、但需要了解 AutoCAD API 的开发人员条件下：

| 范围 | 粗略工作量 |
| --- | --- |
| pyautocad 单 DWG POC | 2～4 个工作日 |
| Python 领域逻辑、Excel、校验和单元测试 | 1～2 周 |
| Core Console Python 调度器 | 1～2 周 |
| PySide6 界面、打包和用户验收 | 1～2 周 |
| SSO COM DST 实现 | 2～4 周 |
| 重写 AutoCAD .NET 插件 | 额外 2～6 周，取决于现有插件源码和签名插入逻辑 |

推荐的混合重构达到可替代现有主程序，整体约 4～8 人周。完全移除两个自研 DLL 可能达到 8～14 人周或更高。

这些估算不包含模板修复、AutoCAD 升级、组织代码签名和大规模用户培训。

## 13. 验收指标

### 功能一致性

- 相同 Excel 输入产生相同图纸数量。
- 每个 DWG 的布局名、顺序和数量一致。
- 文件名、图号和 DST 图纸编号一致。
- 图纸集/图纸自定义属性一致。
- 封面、扉页、送审版和多布局行为一致。
- 外参/电子签名结果一致。
- DST 能由 AutoCAD Sheet Set Manager 正常打开，无丢失引用。

### 数据完整性

- 每个 DST 图纸引用都有非空布局 Handle。
- Handle 对应目标 DWG 中的实际布局。
- 期望布局数、实际布局数和 DST 图纸数一致。
- 任一关键任务失败时不输出最终 DST，或明确标记为失败产物。

### 稳定性

- 连续运行不少于 20 个标准项目，无残留 AutoCAD/Core Console 进程。
- 失败任务可以单独重试，不必重跑整个项目。
- 异常退出后可以安全恢复，不破坏既有输出目录。

### 性能

- 在相同机器、模板和 AutoCAD 版本下记录现状基线。
- 混合重构后的总耗时不应显著差于当前 Core Console 方案。
- 并发数应通过压力测试确定，不能直接沿用 `session=10`。

### 可维护性

- 纯业务逻辑单元测试覆盖核心命名和展开分支。
- 测试/正式生成不再维护两套重复实现。
- 配置和输入错误在启动 AutoCAD 前报告。
- 所有第三方和自研依赖均有版本、来源和许可记录。

## 14. 主要风险与缓解措施

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| pyautocad 长期未维护 | Python/COM 兼容问题 | 不作为核心依赖；必要时只借鉴源码，封装自己的 COM 适配器 |
| AutoCAD 2016 版本较旧 | 现代 Python/comtypes 配合不确定 | POC 固定 Python 版本和 32/64 位，形成可复现环境 |
| 布局模板导入不完全等价 | DWG 内容缺失 | 保留 `-LAYOUT Template` 或在 .NET 插件实现 |
| `Ainsert` 的 COM 等价实现未经验证 | 签名/外参结果不一致 | 按已确认源码语义实现，并用多布局 DWG 做前后差异测试 |
| COM 多实例不稳定 | 批量任务串扰或卡死 | 主流程保留 Core Console；COM 只用于单任务/SSO |
| DST COM 锁使用错误 | DST 损坏或提交失败 | 严格实现 LockDb/UnlockDb，使用集成测试和回滚 |
| 一次性重写范围过大 | 长期无法交付 | 旧/新适配器并存，按阶段替换 |
| 缺少当前行为基线 | 无法判断重构是否正确 | 阶段 0 建立黄金样本和性能基线 |

## 15. 最终决策建议

### 建议采用

- Python 作为新的业务编排和应用层语言。
- `openpyxl + Pydantic + pytest` 建立可验证的输入和领域逻辑。
- Python 生成 `.scr` 并调用 `accoreconsole.exe`，保留当前后台并发模式。
- 短期复用 `AutoCad Utility.dll` 和 `UtilityClass.dll`。
- 中期以 SSO COM API 替换 DST XML/DLL 转换。
- 如果需要升级 AutoCAD，优先重新编译/重写版本匹配的 .NET 插件。

### 不建议采用

- 不建议把 `pyautocad` 作为全系统核心依赖。
- 不建议直接用桌面 AutoCAD COM 替换全部 Core Console 任务。
- 不建议在未建立黄金样本前一次性重写。
- 不建议在未完成 `Ainsert` 多布局等价性测试前移除现有插件。

### 一句话结论

Python 重构值得做；pyautocad 只适合做局部验证或交互式适配器。项目真正需要保留的是 Core Console 批处理能力，真正需要重构的是业务逻辑、校验、错误处理、测试和 DST 的官方 API 接入方式。

## 16. 参考资料

- [pyautocad 官方文档](https://pyautocad.readthedocs.io/en/latest/)
- [pyautocad API 源码](https://pyautocad.readthedocs.io/en/latest/_modules/pyautocad/api.html)
- [pyautocad PyPI](https://pypi.org/project/pyautocad/)
- [pyautocad GitHub](https://github.com/reclosedev/pyautocad)
- [pyautocad 提交记录](https://github.com/reclosedev/pyautocad/commits/master/)
- [Autodesk：ActiveX Automation 开发说明](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Customization/files/GUID-2090E4E8-9AE0-4E01-B5EB-0843A30EB0E9.htm)
- [Autodesk：Layout ActiveX 对象](https://help.autodesk.com/cloudhelp/2023/DEU/AutoCAD-ActiveX-Reference/files/GUID-EFC848F1-26BE-4EFA-BC0E-11F874D73842.htm)
- [Autodesk：LAYOUT 命令](https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Core/files/GUID-BCE3AD90-9DE0-488C-9CA4-5FDB9401DCE0.htm)
- [Autodesk：AttachExternalReference](https://help.autodesk.com/cloudhelp/2024/DEU/AutoCAD-LT-ActiveX-Reference/files/GUID-28CB9C44-08E6-47EF-A982-8F505D8C68F6.htm)
- [Autodesk：Sheet Set Manager 对象模型](https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-ActiveX-SSO/files/GUID-56F608AE-CEB3-471E-8A64-8C909B989F24.htm)
- [Autodesk：修改 Sheet Set 的规范](https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-ActiveX-SSO/files/GUID-6D7E2FAD-BA29-4123-B4DF-52F9EE6E6AA7.htm)
- [Autodesk：创建或打开 Sheet Set Database](https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-ActiveX-SSO/files/GUID-A72E5F7E-D18F-4171-8D30-58FEFCC76E03.htm)
