---
id: RES-SH-004
title: AutoCAD 2025 及以上版本迁移分析
status: accepted
owners: [shared]
created: 2026-07-15
updated: 2026-08-17
---

# AutoCAD 2025 及以上版本迁移分析

## 1. 分析范围

本文分析 `plugin/` 下现有 C# 项目如何适配 AutoCAD 2025 及以上版本：

- `AutoCad Utility`
- `CoordinateDimension`
- `Transform`
- `UtilityClass`

分析基线为 2026-07-15 的仓库源码。本文件仅给出迁移方案、兼容边界、风险和验证建议，不代表已经实施代码迁移。

与当前插件源码、构建和测试约定配套的资料见 [AutoCAD 插件开发与交接文档](../guides/GUIDE-SH-001-autocad-plugin-development.md)。

## 2. 结论摘要

现有业务代码不需要推倒重写，但不能把当前 .NET Framework 4.8 DLL 直接用于 AutoCAD 2025，也不能仅替换 `AcMgd.dll` 等引用。

正确方向是：

1. 保留当前旧版 AutoCAD 构建。
2. 把三个 AutoCAD 插件项目转换为 SDK 风格项目。
3. 为 AutoCAD 2025/2026 生成 `net8.0-windows`、x64 构建。
4. 为 AutoCAD 2027 单独准备 `net10.0-windows`、x64 构建。
5. 共享业务源码，但不同运行时和 AutoCAD SDK 必须生成不同 DLL。
6. `UtilityClass` 暂时保留 .NET Framework 4.8 构建，避免破坏现有 Windows PowerShell 5.1 主程序。

当前源码主要使用稳定的 AutoCAD 数据库、事务、布局、外参、选择集、Jig 和矩阵 API。迁移工作量预计更多集中在项目格式、程序集引用、版本化部署和真实 AutoCAD 回归测试，而不是业务算法重写。

## 3. AutoCAD 与 .NET 版本边界

| AutoCAD | AutoCAD 发布号 | 运行时 | 建议插件目标 | SDK 策略 |
| --- | --- | --- | --- | --- |
| 2024 及以前 | R24.x 及以前 | .NET Framework | `net48` 或对应旧框架 | 使用对应旧版 SDK |
| 2025 | R25.0 | .NET 8 | `net8.0-windows`、x64 | 使用 AutoCAD 2025 SDK |
| 2026 | R25.1 | .NET 8 | `net8.0-windows`、x64 | 可使用 AutoCAD 2025 或 2026 SDK |
| 2027 | R26.0 | .NET 10 | `net10.0-windows`、x64 | 使用 AutoCAD 2027 SDK |

Autodesk 明确要求 AutoCAD 2025 的托管插件迁移到 .NET 8 并重新构建。AutoCAD 2026 官方支持 AutoCAD 2025 和 2026 Managed .NET SDK，因此一个基于 AutoCAD 2025 SDK 的 .NET 8 构建可以作为覆盖 2025/2026 的候选版本，但仍必须分别进行运行验证。

AutoCAD 2027 已进入 .NET 10 代际，因此不能把 AutoCAD 2025 的 .NET 8 DLL 当成面向所有未来 AutoCAD 版本的永久通用包。

参考资料：

- [Autodesk：Managed .NET 兼容性](https://help.autodesk.com/view/OARX/2026/ENU/?guid=GUID-A6C680F2-DE2E-418A-A182-E4884073338A)
- [Autodesk：AutoCAD 2025 插件迁移到 .NET 8](https://blog.autodesk.io/autocad-2025-dotnet8-migration/)
- [Autodesk：AutoCAD 2027 安装要求](https://help.autodesk.com/cloudhelp/2027/ENU/AutoCAD-ReleaseNotes/files/installation/INSTALLATION_REQUIREMENTS_AUTOCAD_2027.html)

## 4. 当前项目与目标环境的差距

### 4.1 项目格式

三个 AutoCAD 项目都是旧式非 SDK 风格 `.csproj`，目标框架为 .NET Framework 4.8：

- `plugin/AutoCad Utility/AutoCad Utility/AutoCad Utility.csproj`
- `plugin/CoordinateDimension/coordinatedimension/coordinatedimension.csproj`
- `plugin/Transform/Transform/Transform.csproj`

项目中仍有 `ToolsVersion`、显式 `Compile Include`、旧式资源配置和旧项目类型 GUID。Autodesk 的 AutoCAD 2025 示例使用 Visual Studio 2022、SDK 风格类库和 .NET 8。

### 4.2 AutoCAD 引用

三个项目引用：

```text
AcCoreMgd
AcDbMgd
AcMgd
```

这些引用没有 `HintPath`，实际通过 `.csproj.user` 中的个人环境路径解析：

```text
C:\Program Files\Autodesk\AutoCAD 2016
C:\Program Files\Autodesk\inc-x64
```

调试启动程序也硬编码为 AutoCAD 2016。该方式不可复现，不适合同时维护多个 AutoCAD 版本。

迁移后应优先引用对应版本 ObjectARX SDK 的 `inc` 目录，并继续保持 Autodesk 程序集 `Copy Local=False`，避免把 AutoCAD 自带 DLL 复制到插件输出目录。

参考资料：

- [Autodesk：创建 AutoCAD .NET 8 项目](https://help.autodesk.com/cloudhelp/2025/CHS/OARX-DevGuide-Managed/files/GUID-23E33075-3C36-48CA-B937-B85606B77F71.htm)
- [Autodesk：引用 AutoCAD Managed .NET API](https://help.autodesk.com/cloudhelp/2025/PTB/OARX-DevGuide-Managed/files/GUID-2363CE7C-AC2B-4CAC-AE5D-F77B386132D7.htm)

### 4.3 平台目标

当前 Debug 配置显式为 x64，但 Release 配置没有统一设置。迁移后 Debug、Release 和所有年度构建都应明确使用 x64。

### 4.4 程序集版本

三个 AutoCAD 项目使用：

```csharp
[assembly: AssemblyVersion("1.0.*")]
```

SDK 风格项目默认自动生成程序集属性。如果直接转换项目，可能与现有 `AssemblyInfo.cs` 产生重复属性；通配版本也不利于确定性构建和问题追踪。

迁移时需要二选一：

- 暂时关闭 SDK 自动生成程序集属性，继续读取现有 `AssemblyInfo.cs`；或
- 把版本和元数据迁移到 SDK 项目属性中，并删除重复定义。

长期应采用明确、可追溯的版本号，不再使用 `1.0.*`。

## 5. 推荐的构建结构

### 5.1 不追求单 DLL 跨运行时

.NET Framework、.NET 8 和 .NET 10 是不同运行时代际，不应尝试让一个 DLL 同时覆盖全部 AutoCAD 版本。

建议形成以下构建结构：

```text
共享业务源码
├─ Legacy 构建
│  └─ net48 + 旧版 AutoCAD SDK
├─ AutoCAD 2025/2026 构建
│  └─ net8.0-windows + AutoCAD 2025 SDK
└─ AutoCAD 2027 构建
   └─ net10.0-windows + AutoCAD 2027 SDK
```

### 5.2 多目标项目与发布分支

Autodesk 给出了通过条件化构建配置支持 `net48` 和 `net8.0-windows` 的示例，同时更推荐按 AutoCAD 年度版本维护发布分支。

对当前代码规模，推荐优先采用“共享源码 + 独立年度宿主项目或构建配置”：

- 业务类只维护一份。
- 每个宿主项目只负责目标框架、AutoCAD SDK 引用、输出目录和版本号。
- 只有 AutoCAD API 确实发生差异时，才增加少量条件编译或版本适配层。
- 当年度差异明显增多后，再为旧版建立长期维护分支。

不建议在一个项目中声明多个目标框架，却无条件引用同一套 AutoCAD DLL；每个目标必须引用与该 AutoCAD/运行时匹配的 SDK。

参考资料：[Autodesk：AutoCAD 插件的 .NET 4.8/.NET 8 多目标策略](https://blog.autodesk.io/multi-targeting-autocad-net-plugin-for-net-48-and-net-80/)

## 6. AutoCAD 2025/2026 项目设置方向

三个 AutoCAD 插件的现代构建至少需要以下能力：

- SDK 风格类库项目。
- `TargetFramework=net8.0-windows`。
- x64 平台。
- `Microsoft.WindowsDesktop.App` 框架引用。
- AutoCAD 2025 的 `AcCoreMgd.dll`、`AcDbMgd.dll`、`AcMgd.dll`。
- Autodesk 引用 `Private=False`/`Copy Local=False`。
- 明确的版本号和输出目录。
- AutoCAD 2025 `acad.exe` 调试启动配置。
- Visual Studio 调试器类型使用 Managed .NET Core。

如果项目确实编译 WPF 或 WinForms，再分别启用：

```text
UseWPF=true
UseWindowsForms=true
```

不能仅因为旧项目带有 WPF 项目类型 GUID 就默认启用所有 UI 文件，应先确认它们是否真正属于产品功能。

## 7. 各项目迁移评估

### 7.1 `AutoCad Utility`

迁移难度：代码层较低，业务回归风险高。

该项目没有第三方 NuGet 依赖，主要使用常规 AutoCAD API：

- 数据库和事务；
- 块表和外部参照；
- 布局和布局管理器；
- 选择集；
- DBText、MText、属性和字段；
- 文件输入输出。

预计大部分源码可以在更新项目格式和 API 引用后继续编译。真正的验收重点是主业务命令：

| 命令 | 迁移后必须验证的内容 |
| --- | --- |
| `dellayouts` | 事务结束后的布局名访问、只保留 Model、Core Console 稳定性 |
| `GetLayoutHandles` | 中文布局名、系统编码、输出路径、句柄可回查 |
| `Ainsert` | 多布局、重复同名外参定义、布局块表记录和保存结果 |
| `BindXrefs` | 已加载、卸载、缺失外参的处理 |
| `FTT` / `FTTA` | DBText、MText、动态/静态属性块字段 |
| `clearxref` | 模型、布局和嵌套块中的引用删除 |

`dellayouts`、`GetLayoutHandles`、`Ainsert` 由主 PowerShell 流程在 Core Console 中调用，因此必须同时验证桌面 AutoCAD 2025 和 `accoreconsole.exe`，不能只验证 `NETLOAD` 成功。

### 7.2 `CoordinateDimension`

迁移难度：中等。

业务代码主要依赖：

- `DrawJig` / `WorldDraw`；
- UCS/WCS 矩阵；
- AutoCAD `DataTable` 和 Named Objects Dictionary；
- DBText、Line 和模型空间写入。

主要迁移风险如下。

#### SDK 默认文件通配

当前目录存在空的 `Form1/2`、`Window1/2`，但旧 `.csproj` 没有编译它们。SDK 风格项目默认自动包含源码和部分资源，如果直接转换，可能意外编译这些 WinForms/WPF 草稿。

迁移时应：

- 显式排除这些文件；或
- 禁用默认项目项并保留明确文件清单；或
- 在确认产品需要界面后，正式选择 WPF 或 WinForms 并纳入设计。

#### 图内配置兼容

插件把字高和高程数量级保存在 DWG 的 `GCLZBConfig` DataTable 中。必须用 AutoCAD 2025 打开旧版 DWG，验证配置能够读取、修改和保存，避免升级后每张旧图都重新初始化。

#### Jig 和 UCS

需要覆盖：

- 世界坐标系；
- 顺时针和逆时针旋转 UCS；
- 标注点左侧和右侧拖动；
- 三条命令 `ZB`、`ZBH`、`ZBA`；
- 文字不倒置、引线不偏移和坐标值不交换。

#### 字体

`txtd.shx` 和 `hztxt.shx` 必须加入 AutoCAD 2025/2026 的支持路径或随 bundle 正确部署。

### 7.3 `Transform`

迁移难度：代码层较低，数据安全风险高。

项目使用 Win32 `kernel32` INI API。该方式仍可在 `net8.0-windows` 下使用，但需要明确 Windows 目标，并可能出现 Windows 平台兼容性分析警告。

主要风险不是 .NET 8，而是既有配置和事务问题：

- 源码读取的 INI 节名与现有 `bin/Debug/config.ini` 不一致；
- `config.ini` 没有纳入项目输出；
- `CoT/UCoT` 直接处理模型空间全部实体；
- 单个实体失败后其他实体仍可能提交，形成部分转换；
- 正向和恢复命令的无配置默认参数不是同一组数值。

因此迁移验收必须以测量控制点和往返误差为标准，至少记录：

- 原始控制点；
- 正向目标坐标；
- `CoT -> UCoT` 往返误差；
- 支持的实体类型；
- 某一实体失败时是否整体回滚。

不能只以“命令可执行”作为通过条件。

### 7.4 `UtilityClass`

`UtilityClass.dll` 不由 AutoCAD 加载，而是由 `Functions.ps1` 在 Windows PowerShell 5.1 进程中通过 `Add-Type` 加载。

Windows PowerShell 5.1 基于 .NET Framework。若把当前 `UtilityClass.dll` 直接替换为纯 `net8.0` DLL，现有 PowerShell 主程序会失去兼容性。

因此建议：

- 继续保留 `net48` 版本供 Windows PowerShell 5.1 使用；
- 如未来迁移到 PowerShell 7.4，可额外提供 `net8.0-windows` 版本；
- 不把 AutoCAD 2025 插件升级和 PowerShell 7 升级合并成一次改造；
- DST 编解码逻辑保持独立，不需要因为 AutoCAD 宿主升级而变更格式。

参考资料：[Microsoft：Windows PowerShell 5.1 与 PowerShell 7.x 的运行时差异](https://learn.microsoft.com/en-us/powershell/scripting/whats-new/differences-from-windows-powershell?view=powershell-7.5)

## 8. 主 PowerShell 程序的适配边界

当前 `config.ini` 固定指向：

```text
C:\Program Files\Autodesk\AutoCAD 2016\accoreconsole.exe
```

主脚本固定加载：

```text
Libs\AutoCad Utility.dll
```

### 8.1 只支持 AutoCAD 2025/2026

如果产品决定完全切换到 2025/2026，可以让配置指向对应 Core Console，并让固定 DLL 路径指向 .NET 8 构建。

### 8.2 同时支持旧版和新版

如果需要保留旧版，应按 AutoCAD 版本存放不同 DLL，例如：

```text
Libs/
├─ AutoCAD2016/AutoCad Utility.dll
├─ AutoCAD2025/AutoCad Utility.dll
└─ AutoCAD2027/AutoCad Utility.dll
```

主程序根据配置的 `accoreconsole.exe` 或实际文件版本选择对应插件。不能在旧版 AutoCAD 和 AutoCAD 2025 之间共用同一个物理 DLL。

`UtilityClass.dll` 可继续保留在当前 `Libs/`，因为它属于 PowerShell 进程而不是 AutoCAD 进程。

## 9. 发布与加载策略

### 9.1 主流程插件

`AutoCad Utility.dll` 可以继续由生成的 `.scr` 使用 `NETLOAD` 加载，但应：

- 使用与 Core Console 版本匹配的 DLL；
- 把插件目录加入受信任路径；
- 正式发布时进行数字签名；
- 避免长期通过脚本把 `SECURELOAD` 设置为 0。

### 9.2 人工交互插件

`CoordinateDimension` 和 `Transform` 建议采用 `.bundle`：

```text
Company.Plugin.bundle/
├─ PackageContents.xml
└─ Contents/
   ├─ 2025/
   ├─ 2026/
   └─ 2027/
```

`PackageContents.xml` 用 `RuntimeRequirements` 限制版本和平台：

| 版本 | Series |
| --- | --- |
| AutoCAD 2025 | `R25.0` |
| AutoCAD 2026 | `R25.1` |
| AutoCAD 2027 | `R26.0` |

同时设置：

```text
OS="Win64"
Platform="AutoCAD"
```

如果明确支持所有基于 AutoCAD 的行业产品，可在经过实际验证后使用 `Platform="AutoCAD*"`。

参考资料：

- [Autodesk：RuntimeRequirements 元素](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Customization/files/GUID-1591CA01-EF87-48CD-952B-772FE26037F1.htm)
- [Autodesk：插件 bundle 安装和安全](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Customization/files/GUID-5E50A846-C80B-4FFD-8DD3-C20B22098008.htm)

## 10. 测试与验收矩阵

### 10.1 构建检查

每个支持版本都应验证：

- Debug x64 构建；
- Release x64 构建；
- AutoCAD 引用没有复制到输出目录；
- 输出目录只包含插件自身及必要依赖；
- 程序集版本、目标框架和 AutoCAD SDK 版本可追溯；
- 2025 构建不会被错误加载到旧版 AutoCAD。

### 10.2 加载检查

- 桌面 AutoCAD `NETLOAD` 成功；
- Core Console `NETLOAD` 成功；
- `ExtensionApplication.Initialize()` 不抛异常；
- 命令可被识别；
- 没有 `FileLoadException`、`TypeLoadException`、`MissingMethodException`；
- 从受信任路径和 bundle 加载行为正确。

### 10.3 业务回归

| 项目 | 必测内容 |
| --- | --- |
| AutoCad Utility | 布局清理、模板布局、句柄文本、Ainsert、多布局、字段、外参 |
| CoordinateDimension | 三种标注、左右拖动、旋转 UCS、旧 DWG 配置、字体 |
| Transform | 控制点、正向/恢复、往返误差、异常回滚、配置文件 |
| UtilityClass | DST/XML 往返、PowerShell 5.1 加载和主流程 |

### 10.4 主流程黄金样本

应建立固定的 Excel、DWG、外参和 DST 样本，分别在 AutoCAD 2016/旧版和 AutoCAD 2025/2026 下运行，比较：

- 生成的 DWG 数量和布局数量；
- 布局名及句柄映射；
- 外参插入位置和数量；
- DST 中的子集、图纸、图号、布局关联；
- AutoCAD/Core Console 日志；
- 总耗时和失败重试行为。

## 11. 推荐实施顺序

### 阶段 0：冻结基线

1. 归档当前旧版 DLL、源码、文件哈希和最小业务样本。
2. 记录当前 AutoCAD 2016 主流程结果。
3. 不覆盖现有 `Libs/AutoCad Utility.dll`。

### 阶段 1：打通核心流程

1. 先迁移 `AutoCad Utility` 到 .NET 8。
2. 使用 AutoCAD 2025 SDK 构建 x64 DLL。
3. 在 AutoCAD 2025 Core Console 中验证主流程三条关键命令。
4. 完成端到端 DWG/DST 黄金样本比较。

### 阶段 2：迁移独立插件

1. 迁移 `CoordinateDimension`，处理 SDK 默认文件通配和 UI 草稿。
2. 迁移 `Transform`，先统一配置和坐标验收标准。
3. 为两个插件建立 bundle 和真实图形回归测试。

### 阶段 3：多版本发布

1. 建立旧版、2025/2026、2027 的独立输出目录。
2. 让主程序选择与 Core Console 匹配的 DLL。
3. 在 `PackageContents.xml` 中限定 AutoCAD Series。
4. 建立自动构建、版本记录和发布检查。

### 阶段 4：可选现代化

1. 评估 PowerShell 7.4。
2. 为 `UtilityClass` 增加 .NET 8 构建。
3. 在 PowerShell 7、WPF、EPPlus、DocX、iText 全部通过回归后，再考虑替换 Windows PowerShell 5.1。

## 12. 风险优先级

### P0

- 旧版和新版 AutoCAD 加载了错误运行时的 DLL。
- `Transform` 配置格式不一致导致使用错误坐标参数。
- 主流程在 Core Console 中能够加载 DLL，但布局、句柄或外参结果已经变化。
- `UtilityClass` 被错误替换为 .NET 8 DLL，导致 Windows PowerShell 5.1 无法启动。

### P1

- SDK 风格项目意外编译 `CoordinateDimension` 的 UI 草稿。
- AutoCAD API 引用仍依赖个人 `.csproj.user` 路径。
- Debug/Release 平台目标不一致。
- 旧 `AssemblyInfo.cs` 与 SDK 自动生成属性冲突。
- bundle 没有正确限制 AutoCAD Series。

### P2

- 继续使用通配程序集版本。
- 没有自动构建和命令级回归测试。
- 依靠关闭 `SECURELOAD` 加载未签名插件。
- 多个年度 DLL 使用相同目录和文件名，发布时容易互相覆盖。

## 13. 最终建议

最稳妥的路线不是“一次性把整个仓库升级到 .NET 8”，而是按进程边界拆分：

```text
Windows PowerShell 5.1 进程
└─ 继续使用 net48 UtilityClass.dll

AutoCAD 2025/2026 进程
└─ 使用 net8.0-windows AutoCAD 插件

AutoCAD 2027 进程
└─ 使用 net10.0-windows AutoCAD 插件
```

优先迁移并验证主流程依赖的 `AutoCad Utility`，再迁移两个独立工具。对当前项目而言，框架升级本身不是最大风险；最大风险是加载到错误版本、Core Console 行为变化、坐标参数错误以及缺少可比较的黄金样本。

