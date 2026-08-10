# 开发与交接文档

## 1. 项目定位

本项目用于从 Excel 中的“图纸集属性 + 图纸分组清单”生成一套市政专业设计成果框架。核心产物包括：

- 每个图纸分组对应的一个 DWG 文件；一个 DWG 可包含一个或多个布局。
- `图纸集数据文件.dst`，其中保存图纸集、子集、图纸、自定义属性和布局引用。
- `图纸目录.xlsx`。
- 正式生成时复制的 `材料表.xlsx`。

程序不是 AutoCAD 插件宿主，而是 WPF 前端加 PowerShell 调度器。它生成 `.scr` 脚本，再并行启动 `accoreconsole.exe`；AutoCAD 进程内通过 `AutoCad Utility.dll` 提供的命令完成布局清理、布局句柄采集和外部参照插入。

## 2. 当前基线与运行边界

分析基线为 2026-07-15 的工作目录内容。该目录当前不是 Git 工作区。

推荐运行环境：

| 项目 | 要求/现状 |
| --- | --- |
| 操作系统 | Windows 11；WPF 与 AutoCAD 均依赖 Windows |
| PowerShell | 优先 Windows PowerShell 5.1；已验证 `Functions.ps1` 可加载 |
| AutoCAD | 配置指向 AutoCAD 2016 Core Console；本机该路径存在 |
| AutoCAD 托管 API | `AutoCad Utility.dll` 依赖 `Acdbmgd, Version=20.1.0.0`，应与 AutoCAD 2016 对齐 |
| Excel | 不要求安装 Excel，代码使用 EPPlus 5.2.0 直接读写 `.xlsx` |
| 脚本编码 | INI、AutoCAD 脚本和部分临时文件依赖系统默认编码，当前内容以中文 Windows 环境为前提 |
| 权限 | 输出目录、项目 `log/`、`temp/` 和系统临时目录必须可写 |

### 启动前必须处理的问题

1. 主脚本第 73 行硬编码 `$config_filename = "config0.24.ini"`，但仓库中只有 `config.ini`。应统一文件名；在完成代码修复前，可在本地受控环境复制一份同内容的 `config0.24.ini` 做验证。
2. `图纸集生成-市政用0.24.ps1` 和 `Functions.ps1` 的 Authenticode 状态均为 `HashMismatch`。代码修改后应移除失效签名块或使用有效证书重新签名，不能把 `Bypass` 当成长期方案。
3. 示例 Excel 中包含其他机器的绝对 DWG 路径，正式运行前必须替换 `基础模板`、`电子签名参照文件` 和 `图纸保存路径`。

## 3. 目录与职责

```text
autocad-sheetset/
├─ 图纸集生成-市政用0.24.ps1  # 主程序：WPF、业务规则、生成流程
├─ Functions.ps1             # 公共函数与依赖加载
├─ config.ini                # 运行配置（当前与主脚本期望文件名不一致）
├─ InputFiles/               # 项目 Excel 示例/输入文件
├─ Templates/
│  ├─ Szmedi/                # 默认 DWG 模板与基础模板
│  ├─ User/                  # 用户自定义 DWG 模板
│  └─ 材料表.xlsx             # 正式生成时复制到输出目录
├─ Libs/                     # EPPlus、DocX、iText、自研 DLL
├─ log/                      # AutoCAD Core Console 汇总日志
└─ temp/                     # 临时工作目录；正式/测试流程末尾会清空其中内容
```

`Templates/Szmedi/` 当前还包含 `.bak`、`.dwl`、`.dwl2` 文件，应视为编辑残留，不是运行依赖。清理前先确认没有人正在编辑对应 DWG。

## 4. 系统结构与调用链

```mermaid
flowchart LR
    UI[WPF 主界面] --> EXCEL[EPPlus 读取 SheetSet / Sheet]
    EXCEL --> RULES[图纸编号、文件名、模板和子集规则]
    RULES --> SCR[生成 DWG 副本与 AutoCAD .scr]
    SCR --> CORE[accoreconsole.exe 并行执行]
    CORE --> ADDIN[AutoCad Utility.dll 命令]
    ADDIN --> HANDLE[布局句柄文本]
    RULES --> XML[DST 中间 XML]
    HANDLE --> XML
    XML --> DST[UtilityClass.dll 转换为 .dst]
    RULES --> LIST[图纸目录.xlsx]
```

正式“生成”流程：

1. 加载 `Functions.ps1` 和 INI 配置，检查基础模板、Core Console、自研 AutoCAD DLL。
2. 用户选择 Excel；程序读取 `SheetSet`，在界面显示项目名称。
3. 读取 `Sheet`，把每行“分组”按 `张数` 展开成具体图纸/布局记录。
4. 按每行的 `模板类型` 和 `图幅` 选择 DWG 模板及其中的布局。
5. 在输出目录创建/备份文件，复制基础 DWG，并为每个 DWG 生成同名 `.scr`。
6. `AcadScript` 按 `session` 分批并行运行 Core Console。
7. 合并插件产生的布局句柄文本，并回填每张图纸的 `AcDbHandle`。
8. 组装 AutoCAD Sheet Set XML，通过 `UtilityClass.DstViewer.XmlToDst` 输出 `.dst`。
9. 生成 `图纸目录.xlsx`，复制 `材料表.xlsx`，清理 `.scr`、`.txt`、`.bak` 等临时文件并打开输出目录。

“测试”按钮复用了大段正式流程，但输出路径会追加 `_TEST`，DST 名称为 `图纸集数据文件_TEST.dst`。当前测试分支只为起始序号为 `0` 或 `1` 的分组落地 DWG/脚本，而且不回填布局句柄，不能作为完整的回归测试或正式结果校验。

## 5. 配置文件

当前 `ReadIni` 只提取包含 `=` 的行，忽略节名和注释，最终把所有键放入同一个对象。重复键以后出现的值为准；值本身不应包含 `=`。

| 键 | 当前值 | 用途 |
| --- | --- | --- |
| `accorepath` | `C:\Program Files\Autodesk\AutoCAD 2016\accoreconsole.exe` | Core Console 路径 |
| `session` | `10` | 同一批并发 AutoCAD 进程数，必须为正整数 |
| `布局模板` | `市政项目模板` | 默认模板文件名前缀 |
| `基础模板` | `基础模板.dwg` | 从 `Templates/Szmedi/` 复制的新 DWG 底板 |
| `SerialDigit` | `2` | 图纸流水号总位数 |
| `DefaultLayoutName` | `布局1` | 从基础 DWG 删除的初始布局名 |
| `ExcelFilePath` | 空 | 文件选择器初始目录；空时使用 `InputFiles/` |
| `TempletPath` | 空 | 用户模板目录；空时使用 `Templates/User/` |

注意：自定义 `TempletPath` 只影响用户在界面中选择模板；默认模板仍来自 `Templates/Szmedi/`。

## 6. Excel 输入契约

程序实际读取固定名称的两个工作表：`SheetSet` 和 `Sheet`。示例文件还有 `Config` 页，但 PowerShell 不直接读取它；它主要为 Excel 公式和数据验证提供选项。

### 6.1 `SheetSet` 工作表

该页采用键值表：A 列是属性名，B 列是值。`ReadSheetSet` 会读取到最后一个非空行，并把每一行转成同名 PowerShell 属性。

主流程直接依赖或输出的常见字段：

| 字段 | 必填性 | 说明 |
| --- | --- | --- |
| `工程名称` | 必填 | 参与界面标题和图纸集名称 |
| `设计号` | 建议必填 | 参与界面显示，并作为 DST 自定义属性 |
| `设计阶段` | 必填 | 参与图纸集名称 |
| `专业名称` | 必填 | 参与图纸集名称和目录“专业”列 |
| `专业代码` | 必填 | DWG 文件名和图号前缀，如 `GP`、`RQ` |
| `是否送审版` | 封面存在时必填 | 值为“是”时，封面模板布局名追加“送审” |
| `图纸保存路径` | 必填 | 正式输出目录；测试目录在其后追加 `_TEST` |
| `制图人`、`设计人`、`校对人`、`专业负责人` | 可选 | 有全局值时写入图纸集属性；为空时允许从 `Sheet` 每行补充图纸属性 |
| `编号前缀` | 可选/遗留 | 代码只读取其长度来调整 DST 图纸编号位数；现有样例没有该行 |

除 `图纸保存路径` 外，`SheetSet` 中的所有键值都会写入 DST 的图纸集自定义属性。因此新增普通项目属性通常不需要改代码；但 DWG 模板中的字段必须使用同名属性才能显示。

### 6.2 `Sheet` 工作表

第 1 行必须是字段名，第 2 行起每行代表一个“图纸分组”。

| 列 | 必填性 | 代码含义 |
| --- | --- | --- |
| `起始序号` | 必填 | 整数；分组第一张图的序号。封面/扉页样例使用 `0` |
| `图名` | 必填 | 图纸标题；同名分组会进入特殊的中文序号后缀逻辑 |
| `张数` | 必填 | 正整数；大于 1 时在同一 DWG 中生成多个布局 |
| `图幅` | 必填 | 同时决定图纸属性和模板中的布局名，例如 `A3`、`A3NS` |
| `出图比例` | 建议填写 | 写入图纸自定义属性，空值可能在图框中显示为空 |
| `模板类型` | 必填 | 决定 `{模板前缀}-{模板类型}.dwg`，现有值为封面、扉页、图纸目录、材料表、通用 |
| `制图人`、`设计人`、`校对人` | 条件必填 | 对应 `SheetSet` 全局字段为空时，从这里提供每张图的值 |
| `基础模板` | 可选 | 指定该分组要复制的基础 DWG；不存在时退回默认基础模板。名称容易误解，它不是布局模板 |
| `电子签名参照文件` | 可选 | 非空时由插件命令 `Ainsert` 插入到图纸中 |
| `备注` | 可选 | 写入 DST 图纸属性和图纸目录 |

维护输入文件时必须保证：

- `起始序号 + 张数` 与下一组序号连续且不重叠；代码不会主动校验冲突或断号。
- `张数 > 0`，序号能在 `SerialDigit` 设定的位数内表达。
- `模板类型` 对应的 DWG 文件真实存在。
- 模板 DWG 中存在按下一节规则计算出的布局名。
- 公式单元格要先在 Excel 中完成计算并保存。EPPlus 读取的是文件中已缓存的值，程序不会调用 Excel 重新计算。

### 6.3 示例工作簿中的录入辅助

`Config` 页维护工作阶段、专业及代码、模板类型、图幅列表。示例中：

- `SheetSet!B15` 用 `VLOOKUP` 根据专业名称生成专业代码。
- `SheetSet!B9` 根据版本是否为 `0` 计算“是否送审版”。
- `Sheet` 的模板类型和图幅使用数据验证下拉列表。
- 后续分组的起始序号通常用“上一行起始序号 + 上一行张数”公式生成。

这些规则目前只存在于 Excel 模板，PowerShell 未做等价校验。调整模板时应同步检查公式、缓存值和数据验证范围。

## 7. 模板与命名规则

### 7.1 模板文件

默认布局模板路径为：

```text
Templates/Szmedi/{布局模板前缀}-{模板类型}.dwg
```

例如 `市政项目模板-通用.dwg`。用户在界面中选择自定义模板时，文件名必须匹配：

```text
任意前缀-(封面|扉页|材料表|图纸目录|通用).dwg
```

界面只保存匹配得到的“任意前缀”和文件所在目录，运行时仍会按同一前缀查找其他模板类型。因此一套自定义模板应把所需类型放在同一目录，并保持相同前缀。

### 7.2 模板布局

- `封面`：先从图幅中移除 `NS`；若 `是否送审版 = 是`，再追加 `送审`。
- `扉页`：从图幅中移除 `NS`。
- 其他模板类型：布局名必须与 `图幅` 完全一致。

### 7.3 输出命名

- 布局名：`{补零序号} {图名}`，例如 `03 设计施工说明`。
- 单张分组 DWG：`{专业代码}-{布局名}.dwg`。
- 多张分组 DWG：`{专业代码}-{起始号}-{结束号} {图名}(一)-({中文总张数}).dwg`。
- 图号：`{专业代码}-{补零序号}`。
- DST：正式为 `图纸集数据文件.dst`，测试为 `图纸集数据文件_TEST.dst`。

`Transdigit` 只声明支持 1–999，且 100–999 的中文转换只是逐位数字，不含“百/十”单位。超过 999 返回 `OutOfRange`，这是扩大大型图册前必须改造的边界。

## 8. 关键代码说明

### 8.1 主脚本

| 区域 | 职责 |
| --- | --- |
| XAML 与启动初始化 | 创建 WPF 界面、定位项目根目录、加载函数库和配置 |
| `Get-SheetList` | 把输入分组展开为图纸记录，计算布局名、图号、DWG 文件名和中文分张标题 |
| 界面事件 | 浏览 Excel/模板，触发测试生成或正式生成 |
| DST XML 组装 | 创建图纸集自定义属性、子集、图纸、自定义图纸属性和布局引用 |
| AutoCAD 脚本生成 | 写出 `dellayouts`、`-layout`、`GetLayoutHandles`、`Ainsert` 等命令 |
| 输出整理 | 生成目录 Excel、DST、复制材料表并清理临时文件 |

测试与正式处理器存在约 500 行高度重复代码。修改生成逻辑时必须同时核对两处，优先重构成可参数化的单一函数。

### 8.2 `Functions.ps1` 中当前主流程使用的函数

| 函数 | 作用 |
| --- | --- |
| `ReadIni` | 将简单 `key=value` 文件读成对象 |
| `ReadSheetSet` / `ReadSheet` | 使用 EPPlus 读取两个输入页 |
| `FileToGroup` / `AcadScript` | DWG 分组、并发启动 Core Console、汇总日志 |
| `Prefixname` / `Transdigit` | 编号补零和中文序号转换 |
| `CreateMain` / `CreateSub` / `UpdateValue` | 修改 DST 中间 XML |
| `CheckFolderExist` / `CheckFolder` / `CheckFile` | 路径检查、输出目录创建和旧文件备份 |

其余函数是同一工具库中的扩展能力，包括 DST 反向读取、Word 目录/审批表、PDF 拆分合并、光盘标签和电子文件清单。本主界面当前没有调用这些函数。它们依赖 `DocX` 和 `iText`，所以即使主流程不用，脚本加载时仍会加载相关 DLL。

### 8.3 DLL 依赖

| 组件 | 程序集版本 | 用途 |
| --- | --- | --- |
| EPPlus | 5.2.0.0 | Excel 读写 |
| Xceed.Document.NET / Xceed.Words.NET | 1.4.0.0 | Word 模板处理 |
| iText IO / Kernel | 7.1.11.0 | PDF 处理 |
| PDFSplitter | 1.0.0.0 | PDF 拆分封装 |
| UtilityClass | 1.0.0.0 | DST/XML 双向转换等通用能力 |
| AutoCad Utility | 1.0.7913.16922 | AutoCAD 内部命令；依赖 AutoCAD 2016 托管 API |

第三方许可证位于对应 `Libs/*/license.md` 或 `LICENSE.md`。升级 DLL 前应同时核对许可证、.NET Framework 兼容性以及 AutoCAD 托管 API 版本。

## 9. 输出目录与副作用

`CheckFolder` 的行为需要特别注意：

- 输出目录不存在时直接创建。
- 输出目录已存在且顶层有文件时，把顶层文件移动到 `back(yyyy-MM-dd HH-mm-ss)` 子目录。
- 既有子目录不会被移动或清空。

流程结束时会删除输出目录顶层的 `*.bak`、`*.scr`、`*.txt`，清空项目自身 `temp/` 的全部内容，并删除项目根目录顶层的 `*.log`。AutoCAD 汇总日志写在 `log/`，不会被最后一项匹配。调试失败时，先复制现场文件再手工重跑，避免下一次启动覆盖证据。

程序最后调用 `Invoke-Item $projectpath` 打开资源管理器；在无人值守或 CI 环境中应禁用这一行为。

## 10. 常见故障定位

### 启动后立即提示缺少配置

检查主脚本期望的 `config0.24.ini` 与实际文件名是否一致。这是当前仓库已确认的问题。

### 脚本被执行策略拦截

用 `Get-AuthenticodeSignature` 查看状态。当前签名为 `HashMismatch`；开发时确认来源后可临时放宽当前进程策略，发布时重新签名。

### 找不到模板或布局

依次检查模板目录、模板前缀、`模板类型`、`图幅`，以及送审封面是否存在 `{图幅}送审` 布局。文件存在不代表布局存在。

### DST 中布局打不开或句柄为空

检查：

1. 输出目录是否生成与 DWG 同名的 `.scr`。
2. `log/*脚本执行记录*.log` 中是否有 `netload` 或自定义命令错误。
3. `AutoCad Utility.dll` 是否能被 AutoCAD 2016 加载。
4. `GetLayoutHandles` 是否为每个布局写出了文本记录。
5. 布局名中是否包含插件/INI 解析不支持的字符。

### Excel 修改后程序仍读到旧值

公式可能没有刷新缓存。用桌面 Excel 打开、重新计算并保存；同时确认工作表名仍为 `SheetSet` 和 `Sheet`。

### Excel 文件被锁定

`ReadSheetSet` 会释放工作簿，但 `ReadSheet` 当前没有显式调用 `Dispose()`。发生锁文件时先退出进程；后续应给两个读取函数统一增加 `try/finally` 资源释放。

## 11. 开发与验证建议

当前没有自动化测试。改动时至少执行以下分层验证。

### 11.1 静态语法检查

```powershell
$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path '.\图纸集生成-市政用0.24.ps1'),
    [ref]$tokens,
    [ref]$errors
)
$errors
```

对 `Functions.ps1` 重复一次；无输出才表示语法解析通过。

### 11.2 函数库加载检查

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `
  ". '.\Functions.ps1'; (ReadIni '.\config.ini').session"
```

### 11.3 最小业务样例

准备一个单独的输出目录和最小 Excel：

- 1 张图纸目录，起始序号 1；
- 1 个通用分组，起始序号 2、张数 1；
- 不使用电子签名参照；
- 使用默认模板。

先点“测试”，再点“生成”。核对 DWG 布局、DST 打开状态、布局句柄、图纸属性、`图纸目录.xlsx` 和日志。多布局、同名图纸、送审封面、自定义基础模板及外部参照应分别作为扩展用例测试。

### 11.4 不建议在 CI 中直接做的验证

AutoCAD 2016、WPF 和资源管理器调用都依赖桌面 Windows 环境。应先把纯逻辑（Excel 校验、图纸展开、XML 生成、命名规则）拆成无 UI/无 AutoCAD 的函数并建立 Pester 测试，再把 Core Console 运行保留为专用 Windows 集成测试。

## 12. 扩展维护手册

### 新增图纸集属性

在 `SheetSet` A/B 列新增键值即可进入 DST 图纸集属性。若要显示在 DWG 图框中，还需修改模板字段引用。若该属性参与路径、命名或模板选择，再修改主脚本业务逻辑。

### 新增模板类型

1. 在同一模板目录添加 `{前缀}-{新类型}.dwg`。
2. 在 Excel `Config` 页增加选项并扩展数据验证范围。
3. 如布局名不等于 `图幅`，在主脚本两处模板 `switch` 中加入规则。
4. 同步修改自定义模板文件名正则 `$patten_layout`。
5. 同时验证测试和正式按钮；在完成重构前，两处代码都可能需要修改。

### 修改编号/文件名规则

入口为主脚本 `Get-SheetList`、`Prefixname` 和 `Transdigit`。同时核对：布局名、图号、DWG 文件名、DST `Number`、图纸目录以及同名图纸/多张分组分支，不能只改其中一个表现层。

### 升级 AutoCAD

`AutoCad Utility.dll` 是主要兼容性边界。其源码现已确认位于 `plugin/AutoCad Utility/`，升级时应使用目标 AutoCAD 版本的 `AcCoreMgd.dll`、`AcDbMgd.dll`、`AcMgd.dll` 重新编译，并验证 `dellayouts`、`GetLayoutHandles`、`Ainsert` 三个命令。仅修改 `accorepath` 通常不够。完整源码说明见 [AutoCAD 插件开发与交接文档](PLUGIN_DEVELOPMENT.md)。

## 13. 已知技术债与建议优先级

### P0：先恢复可运行基线

- 统一 `config0.24.ini` / `config.ini` 文件名。
- 处理失效代码签名。
- 用最小样例完整验证 AutoCAD 2016、插件命令和 DST 输出。
- 为输入 Excel 增加启动前校验，避免运行数分钟后才因模板、路径或数据错误失败。

### P1：降低误生成和维护风险

- 合并测试/正式两套重复流程，以参数控制输出路径、是否采集句柄和生成范围。
- 给 `ReadSheet` 增加 `Dispose()`，所有 EPPlus/文档/PDF 对象使用 `try/finally`。
- 给每个 Core Console 进程检查退出码；当前代码即使 AutoCAD 命令失败也会继续生成 DST。
- 验证句柄数量与布局数量一致，缺失时停止生成 DST。
- 明确 EPPlus 5 的 `LicenseContext`，并在分发文档中记录实际许可场景。

### P2：建立可持续开发方式

- 把业务逻辑拆为模块，使用 Pester 覆盖编号、同名图纸、多布局、送审模板和 XML。
- 用结构化配置解析替换当前扁平 `ReadIni`。
- 把内嵌 XAML 和 DST 基础 XML 提取为独立文件。
- 移除未使用函数或拆分为独立模块，避免主流程被 Word/PDF 依赖拖累。
- 清理备份、锁文件和示例中的个人绝对路径；建立 `.gitignore` 并纳入版本控制。
