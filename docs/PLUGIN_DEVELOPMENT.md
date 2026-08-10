# AutoCAD 插件开发与交接文档

## 1. 文档范围与结论

本文档覆盖 `plugin/` 下全部 4 个 C# 项目，分析基线为 2026-07-15 的工作目录源码：

| 项目 | 产物 | 定位 | 是否被主 PowerShell 流程使用 |
| --- | --- | --- | --- |
| `AutoCad Utility` | `AutoCad Utility.dll` | 图纸集生成流程所需的 AutoCAD 命令集合 | 是，`NETLOAD` 后调用 |
| `CoordinateDimension` | `coordinatedimension.dll` | 市政节点坐标、标高与引线标注工具 | 否，独立人工交互插件 |
| `Transform` | `Transform.dll` | 模型空间实体的四参数坐标转换/恢复工具 | 否，独立人工交互插件 |
| `UtilityClass` | `UtilityClass.dll` | 分组、INI 和 DST/XML 转换通用库 | 是，由 PowerShell 直接加载 |

四个项目互相没有项目引用，也没有统一解决方案。主程序实际使用的两个 DLL 与源码目录中已有 Debug 产物完全一致：

- `Libs/AutoCad Utility.dll` 与 `plugin/AutoCad Utility/AutoCad Utility/bin/Debug/AutoCad Utility.dll` 的 SHA-256 相同。
- `Libs/UtilityClass.dll` 与 `plugin/UtilityClass/bin/Debug/UtilityClass.dll` 的 SHA-256 相同。

这意味着主程序中的自研二进制已经可以追溯到当前源码。`CoordinateDimension` 和 `Transform` 则是同仓保存、但未接入图纸集生成流程的独立工具。

## 2. 技术基线

### 2.1 公共技术栈

- 操作系统：Windows。
- 语言：C#，旧式非 SDK 风格项目。
- 目标框架：全部为 .NET Framework 4.8。
- IDE/构建：Visual Studio/MSBuild。
- AutoCAD 插件入口：`IExtensionApplication`、程序集级 `ExtensionApplication` 和 `CommandClass` 特性。
- AutoCAD API：`AcCoreMgd`、`AcDbMgd`、`AcMgd`，引用设置为 `Private=False`，发布时不要复制这些 Autodesk 程序集。

三个 AutoCAD 项目的 `.csproj.user` 都把引用搜索路径和调试程序硬编码为：

```text
C:\Program Files\Autodesk\AutoCAD 2016
C:\Program Files\Autodesk\inc-x64
C:\Program Files\Autodesk\AutoCAD 2016\acad.exe
```

当前机器存在 AutoCAD 2016 及三个托管 API DLL，但不存在 `C:\Program Files\Autodesk\inc-x64`。项目仍可借助第一个路径完成构建。换机后若引用失效，应优先通过团队级 MSBuild 属性或明确的开发环境变量统一引用路径，不要继续依赖个人 `.csproj.user`。

项目和现有二进制版本基线如下：

| 项目 | 根命名空间 | Debug 目标 | `AssemblyVersion` 设置 | 现有 Debug DLL 版本 |
| --- | --- | --- | --- | --- |
| AutoCad Utility | `AutoCad_Utility` | x64 | `1.0.*` | `1.0.7913.16922` |
| CoordinateDimension | `coordinatedimension` | x64 | `1.0.*` | `1.0.7057.21244` |
| Transform | `Transform` | x64 | `1.0.*` | `1.0.7682.22266` |
| UtilityClass | `UtilityClass` | AnyCPU | `1.0.0.0` | `1.0.0.0` |

前三个项目使用通配程序集版本，每次构建可能得到不同版本号，不利于可重复发布和问题追踪；`AssemblyFileVersion` 则固定为 `1.0.0.0`。后续应改为由发布流程明确注入统一版本。

### 2.2 已验证构建方式

当前源码已使用 Visual Studio 2022 Community 的 64 位 MSBuild、Debug 配置完成构建验证，4 个项目均成功：

```powershell
$msbuild = 'C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\MSBuild.exe'

& $msbuild '.\plugin\UtilityClass\UtilityClass.csproj' /t:Build /p:Configuration=Debug
& $msbuild '.\plugin\AutoCad Utility\AutoCad Utility\AutoCad Utility.csproj' /t:Build /p:Configuration=Debug
& $msbuild '.\plugin\CoordinateDimension\coordinatedimension\coordinatedimension.csproj' /t:Build /p:Configuration=Debug
& $msbuild '.\plugin\Transform\Transform\Transform.csproj' /t:Build /p:Configuration=Debug
```

应使用 `amd64\MSBuild.exe`。当前环境下用 `Bin\MSBuild.exe` 构建三个 `PlatformTarget=x64` 的 AutoCAD 项目，会在 `GenerateResource` 阶段触发 `MSB4216/MSB4028`；这不是源码编译错误，而是 32/64 位任务宿主不匹配。

Debug 配置显式为 x64，Release 配置没有显式 `PlatformTarget`，会退回 AnyCPU。后续维护应统一 Debug/Release 架构，并用实际 AutoCAD 版本验证加载。

### 2.3 加载和调试

手工验证插件时：

1. 在 Visual Studio 中把启动外部程序设为目标版本的 `acad.exe`。
2. 启动 AutoCAD 后打开测试 DWG。
3. 用 `NETLOAD` 加载目标 DLL。
4. 在命令行执行本文档列出的命令。

仓库没有 `.bundle/PackageContents.xml`、安装器或自动加载注册逻辑，当前发布方式是手工 `NETLOAD`，或者由 PowerShell 生成的 `.scr` 调用 `NETLOAD`。

## 3. 目录和源码边界

```text
plugin/
├─ AutoCad Utility/
│  ├─ AutoCad Utility.sln
│  └─ AutoCad Utility/
│     ├─ AutoCad Utility.csproj
│     ├─ myPlugin.cs              # 加载/卸载生命周期
│     ├─ myCommands.cs            # 全部业务命令
│     └─ Properties/AssemblyInfo.cs
├─ CoordinateDimension/
│  ├─ coordinatedimension.sln
│  └─ coordinatedimension/
│     ├─ coordinatedimension.csproj
│     ├─ myPlugin.cs
│     ├─ myCommands.cs            # 标注模型、Jig、配置和命令
│     ├─ Form1/2.*                 # 未纳入项目的空 WinForms 草稿
│     └─ Window1/2.*               # 未纳入项目的空 WPF 草稿
├─ Transform/
│  ├─ Transform.sln
│  ├─ change.txt
│  └─ Transform/
│     ├─ Transform.csproj
│     ├─ myPlugin.cs
│     └─ myCommands.cs            # INI 读取和坐标转换命令
└─ UtilityClass/
   ├─ UtilityClass.sln
   ├─ UtilityClass.csproj
   └─ Class1.cs                   # 三组通用 API
```

以下内容不属于应维护的源代码：

- `.vs/`、`*.suo`、`*.vsidx`、Copilot/聊天索引。
- `bin/`、`obj/`、`*.pdb` 和编译缓存。
- 各项目根目录的 `debug.log`；内容实际是 Visual Studio 扩展的 WebView 日志，不是插件运行日志。
- `myCommands.Designer.cs` 和 `myCommands.resx` 是模板残留资源。三个资源文件仅包含未被业务代码使用的 `MyCommandLocal` 等示例字符串。

仓库当前没有 `.gitignore`，而且当前目录不是有效 Git 工作区；接入版本控制时应先补充 Visual Studio/.NET 忽略规则，避免继续提交上述产物。

## 4. 命令和公共 API 总表

### 4.1 AutoCAD 命令

命令名不区分大小写。

| DLL | 命令 | 输入 | 主要结果/副作用 |
| --- | --- | --- | --- |
| AutoCad Utility | `BindXrefs` | 无 | 绑定已解析外参，拆离已卸载外参 |
| AutoCad Utility | `FTT` | PickFirst 或人工选择文字/块 | 将所选字段固化为普通文字 |
| AutoCad Utility | `FTTA` | 无 | 扫描全图文字/块并固化字段 |
| AutoCad Utility | `GetLayoutHandles` | 无 | 在 DWG 同目录覆盖生成同名 `.txt` |
| AutoCad Utility | `Ainsert` | 一个 DWG 路径 | 在所有非模型布局的原点附着该外参 |
| AutoCad Utility | `clearxref` | 外参块名 | 删除引用并拆离外参定义 |
| AutoCad Utility | `dellayouts` | 无 | 删除除 `Model` 外的全部布局 |
| CoordinateDimension | `ZB` | 标注点、引出点，可选设置 | 生成 X/Y 坐标、水平线和引线 |
| CoordinateDimension | `ZBH` | 同上 | 在 `ZB` 基础上增加两项标高占位文字 |
| CoordinateDimension | `ZBA` | 同上 | 在 `ZBH` 基础上增加附加说明占位文字 |
| Transform | `CoT` | 无 | 转换模型空间全部实体 |
| Transform | `UCoT` | 无 | 对模型空间全部实体执行恢复变换 |

### 4.2 `UtilityClass` 公共 API

| 类型/方法 | 用途 | 主程序是否使用 |
| --- | --- | --- |
| `Utilities.SortToGroup(ArrayList, int)` | 按固定数量切分列表 | 否 |
| `INIReader.IniReadValue` | 通过 Win32 API 读取 INI | 否 |
| `INIReader.IniWriteValue` | 通过 Win32 API 写入 INI | 否 |
| `INIReader.ExistINIFile` | 判断 INI 是否存在 | 否 |
| `DstViewer.DstToXmlFile` | DST 解码并保存为 XML 文件 | 否 |
| `DstViewer.DstToXml` | DST 解码为 `XmlDocument` | 是，`Functions.ps1` 使用 |
| `DstViewer.XmlFileToDst` | XML 文件编码为 DST | 否 |
| `DstViewer.XmlToDst` | `XmlDocument` 编码并保存为 DST | 是，主脚本使用 |

## 5. `AutoCad Utility` 详解

### 5.1 项目职责和入口

- `myPlugin.cs` 通过 `ExtensionApplication` 注册 `MyPlugin`。
- `Initialize()` 只向当前文档命令行打印 `BindXrefs`、`FTT`、`FTTA` 的提示；没有注册事件或持久资源。
- `myCommands.cs` 通过 4 个 `CommandClass` 注册 `BindXrefs`、`FieldToTextclass`、`GetLayoutHandles` 和 `Ainsert`。后一个类同时承载 `Ainsert`、`clearxref` 和 `dellayouts`。

主 PowerShell 脚本生成 AutoCAD 脚本后，按以下关系使用该 DLL：

```text
PowerShell 生成 .scr
  -> NETLOAD "Libs\AutoCad Utility.dll"
  -> dellayouts
  -> -LAYOUT Template/Rename/Set/Delete
  -> GetLayoutHandles
  -> 可选 Ainsert
  -> QSAVE
```

### 5.2 `BindXrefs`

处理流程：

1. 遍历块表中的全部 `BlockTableRecord`。
2. 把 `IsFromExternalReference && IsResolved` 的记录加入绑定集合。
3. 把 `IsFromExternalReference && IsUnloaded` 的记录加入拆离集合。
4. 一次调用 `Database.BindXrefs(ids, false)`。
5. 逐个调用 `Database.DetachXref(id)` 拆离卸载外参。
6. 输出数量和原始路径，提交事务。

异常会用模态对话框显示。该命令会直接改变外参结构，批处理使用前应准备副本。

### 5.3 `FTT` / `FTTA`

两条命令共用 `convertToText`：

- 选择过滤器接受 `TEXT`、`MTEXT` 和 `INSERT`。
- `FTT` 优先使用 PickFirst 选择集，否则提示人工选择。
- `FTTA` 用 `SelectAll` 扫描整张图。
- `DBText` 和 `MText` 仅在 `HasFields` 时调用 `ConvertFieldToText()`。
- 块参照只有在动态块条件下才遍历属性，并转换含字段的 `AttributeReference`。

字段转换不可逆，转换前应保留原图。当前代码不会处理普通静态属性块中的字段，这是已确认的功能边界。

### 5.4 `GetLayoutHandles`

该命令读取布局字典，排除名为 `Model` 的布局，然后在当前 DWG 同目录创建：

```text
<DWG文件名>.txt
```

文件使用系统默认编码，每行契约为：

```text
布局名=布局对象句柄
```

文件以 `FileMode.Create` 打开，因此同名文件会被覆盖。主 PowerShell 流程依赖该文本把布局名映射回 DST 中的布局句柄；修改文件名、分隔符、编码或 `Model` 过滤规则会影响图纸集生成。

### 5.5 `Ainsert`

源代码已经明确其真实行为：

1. 用文件选择提示接收一个存在的 DWG 路径；`FILEDIA=0` 时可由 `.scr` 直接提供路径。
2. 枚举布局字典并排除 `Model`。
3. 对每个剩余布局调用 `AttachXref`，外参名为输入文件的不带扩展名文件名。
4. 在该布局的块表记录中追加 `BlockReference`。
5. 插入点固定为 `(0, 0, 0)`，未显式设置比例、旋转、图层、颜色或其他属性。

因此它的业务语义是“把同一个电子签名/参照 DWG 附着到所有图纸空间布局”，不是绑定、转块或字段处理。主脚本会在调用前把当前图层设为 `0`。

当前实现每个布局都重复调用一次 `AttachXref`，但使用相同块名。不同 AutoCAD 版本对重复外参定义的处理必须通过多布局样例验证；更稳妥的实现是只附着/获取一次外参定义，再向各布局追加块参照。

### 5.6 `clearxref`

处理流程：

- 要求输入精确的外参块名。
- 从块表确认该外参定义存在。
- 删除全图筛选到的同名 `INSERT`。
- 继续扫描普通块定义，删除其中嵌套的同名块参照。
- 最后调用 `DetachXref` 删除定义。

这是一项破坏性操作。当前实现以名称匹配，不处理用户容易混淆的路径/别名关系，也没有二次确认。

### 5.7 `dellayouts`

命令枚举布局字典，排除 `Model`，再逐个调用 `LayoutManager.DeleteLayout`。图纸集生成脚本依靠它清空模板的既有图纸布局。

当前代码把已由事务打开的 `Layout` 对象保存到列表，并在事务结束后读取 `LayoutName`。虽已被现有流程使用，但这是脆弱的对象生命周期写法；重构时应在事务内只收集字符串布局名，再在事务外删除。

## 6. `CoordinateDimension` 详解

### 6.1 功能结构

`myCommands.cs` 包含三层：

```text
MyCommands
  ├─ 创建/读取图内配置
  ├─ 创建文字样式
  ├─ 创建右侧/左侧标注实体集合
  └─ ZB / ZBH / ZBA 命令编排
        -> Dimjig 交互预览和左右判断
              -> NodeDim 计算文字、线段和定位点
```

### 6.2 `NodeDim` 数据模型

`NodeDim` 根据标注点、初始插入点、字高和高程数量级计算所有几何位置。

坐标文字使用市政/测量常见约定，故意交换 AutoCAD XY 轴的显示标签：

```csharp
X文字 = "X=" + AutoCAD点.Y
Y文字 = "Y=" + AutoCAD点.X
```

数值固定保留 3 位小数。坐标线长度根据 X/Y 两个字符串中较长者估算；标高线长度由字高和“高程数量级”估算。文字宽度估算系数、行距和边距均为类内常量式字段，没有外部配置。

### 6.3 图内持久配置

插件不使用外部配置文件，而是在当前 DWG 的 Named Objects Dictionary 中创建名为 `GCLZBConfig` 的 AutoCAD `DataTable`：

| 列名 | 类型 | 行 | 含义 |
| --- | --- | --- | --- |
| `TextHeight` | Double | 0 | 标注文字高度 |
| `HeightOderOfMagnitude` | Integer | 0 | 高程数量级，源代码保留了 `Oder` 拼写 |

第一次运行时会要求输入两个值；之后命令显示当前设置。输入点提示中的 `S` 关键字可以修改设置。该配置随 DWG 保存，不是应用级或用户级配置。

### 6.4 文字样式和字体依赖

`CreatMyTextStyle()` 查找或创建文字样式 `RQBZ`：

- 小字体：`txtd.shx`
- 大字体：`hztxt.shx`
- 宽度比例：`0.7`

随后将 `Database.Textstyle` 设为该样式。字体文件必须位于 AutoCAD 可搜索路径，否则文字显示会异常。

加载提示中写的是 `RQZB`，实际代码创建的是 `RQBZ`，两者不一致。后续应以代码中的 `RQBZ` 为准并统一提示或命名。

### 6.5 标注实体组合

| 创建方法 | 水平坐标线 | 标高线 | X/Y | 地面/管底标高 | 附加说明 |
| --- | --- | --- | --- | --- | --- |
| `CreateDimOnlyXY` | 1 | 0 | 是 | 否 | 否 |
| `CreateDimWithHeight` / `L` | 1 | 1 | 是 | 是 | 否 |
| `CreateDim` / `L` | 1 | 1 | 是 | 是 | 是 |

标高和附加说明目前只是固定占位文字：`地面标高`、`管底标高`、`附加说明`。命令没有提示用户输入实际标高或说明，使用者需要在生成后手工编辑。

所有新实体最终都写入 `ModelSpace`。实体未显式指定图层、颜色、线型或文字样式 ID，主要继承当前数据库/当前图层状态。

### 6.6 `Dimjig` 交互和 UCS

命令先取一个被标注点，再用 `DrawJig` 动态获取引出点：

- 引出点位于标注点 UCS 右侧时，使用右侧实体集合。
- 位于左侧时，使用左侧标高线定位，并把整体向左平移一个坐标线长度。
- `WorldDraw` 绘制临时引线和标注预览。
- 用户确认后，`TransformEnties()` 把最终矩阵应用到实体，再开启事务写入模型空间。

代码通过当前 UCS 矩阵和 `db.Ucsxdir` 修正旋转方向；注释表明 1.02/1.03 版本曾针对 UCS 旋转正负问题做过修复。修改矩阵乘法、基点变换或左右判断时，必须覆盖世界坐标系、顺时针 UCS、逆时针 UCS以及左右两个拖动方向。

### 6.7 三条命令

- `ZB`：坐标线、X/Y 文字和引线。
- `ZBH`：增加标高线、`地面标高`、`管底标高`。
- `ZBA`：再增加 `附加说明`。

三条命令的编排代码高度重复，差别仅是实体工厂。后续可提取一个带“标注模式”参数的内部方法，减少修复一处遗漏另外两处的风险。

### 6.8 未纳入构建的界面草稿

`Form1/2` 和 `Window1/2` 都是空窗口，且没有出现在 `coordinatedimension.csproj` 的 `Compile`、`Page` 或资源项中，不会进入 DLL，也不会影响命令。它们应删除，或在明确产品需求后按一种 UI 技术重新纳入项目；不要误认为当前插件有设置窗口。

## 7. `Transform` 详解

### 7.1 功能结构

- `INIClass`：直接 P/Invoke `kernel32` 的 `GetPrivateProfileString` / `WritePrivateProfileString`。
- `MyCommands.TransformEntity`：组合平移、绕 Z 轴旋转和缩放矩阵并调用 `Entity.TransformBy`。
- `MyCommands.RecoverEntity`：使用倒数比例、反向角度和反向位移组合恢复矩阵。
- `CoT` / `UCoT`：加载配置，选择模型空间全部实体，逐个应用变换并提交事务。

两条命令都用 DXF 组码 410=`Model` 的过滤器调用 `SelectAll`，因此不是转换用户选择集，而是直接转换当前 DWG 模型空间中的全部实体。布局空间实体不会被处理。

### 7.2 源码期望的配置契约

插件在 `Transform.dll` 同目录查找 `config.ini`，源码实际读取以下节和键：

```ini
[Displacement]
X=391090.57816
Y=2472660.598025

[Rotation]
radian=0.0170603779

[Scale]
scale=0.999997425176
```

所有数值通过当前区域设置下的 `Convert.ToDouble` 解析。配置不存在时使用命令内置默认值；配置存在但格式错误时会打印异常，然后继续使用当时尚未被成功覆盖的变量。

### 7.3 已确认的配置发布缺陷

当前项目存在三套不一致状态：

1. `myCommands.cs` 读取 `Displacement/Rotation/Scale`。
2. `obj/Debug/config.ini` 是上述旧格式，但 `obj` 不是可靠源文件位置。
3. `bin/Debug/config.ini` 使用 `[默认参数]`、`[参数1]`、`[参数2]` 以及 `DX/DY/R/S`，源码完全不会读取这些键。

同时，`Transform.csproj` 没有把任何 `config.ini` 声明为 `Content/None` 并复制到输出目录。因此全新构建不会自动得到配置，现有 `bin/Debug/config.ini` 只是历史遗留文件。

这是该项目的 P0 缺陷：现有多参数配置会触发空字符串转换错误，`CoT/UCoT` 随后实际使用各自硬编码默认值。修复前必须先决定产品需要“单组参数”还是“可选多组参数”，再统一解析器、示例配置、构建复制和命令交互。

### 7.4 默认参数和可逆性

`CoT` 默认值：

```text
基点/位移：(391090.57816, 2472660.598025, 0)
旋转弧度：0.0170603779
比例：0.999997425176
```

`UCoT` 无配置时使用另一组默认值：

```text
基点/位移：(391090.522451, 2472660.716344, 0)
旋转弧度：0.0170593097
比例：0.999997530712
```

因此“无配置时先 `CoT` 再 `UCoT`”不能仅凭源码认定为严格代数逆变换。`change.txt` 只记录“`四参数法提高精度`”，没有参数来源、坐标系定义、控制点、误差或验收阈值。任何参数调整都应由测绘/设计责任人确认，并用已知控制点验证往返误差。

### 7.5 事务和错误语义

每个实体的 AutoCAD 异常会被捕获并继续循环，最后仍提交事务。这意味着部分实体失败时，其他实体的转换会保留，形成部分成功状态。对于全图坐标变换，这一行为风险很高；建议改为：

- 转换前校验参数、比例和对象类型。
- 任一实体失败则中止并回滚整个事务，或者明确输出失败对象清单并让用户确认是否提交。
- 命令开始前提示保存/备份，并输出处理数量。

## 8. `UtilityClass` 详解

### 8.1 `Utilities.SortToGroup`

输入一个 `ArrayList` 和每组数量，按原顺序返回“`ArrayList` 的 `ArrayList`”，最后一组允许不足指定数量。空输入返回空集合。

当前实现没有校验 `NumberOfFiles`，传入 0 会除零，传入负数也没有明确语义。新代码应使用泛型 `IReadOnlyList<T>`/`IEnumerable<T>` 并验证组大小大于 0。

### 8.2 `INIReader`

这是与 `Transform.INIClass` 几乎重复的 Win32 INI 包装：

- 固定 500 字符读取缓冲区。
- 仅适用于 Windows。
- 写入方法不检查 Win32 返回值。
- 没有编码、缺失键、默认值或类型转换封装。

主程序和其他三个项目都没有引用这个类型。后续若继续使用 INI，应统一一个实现并为键缺失、数字格式和编码建立明确契约。

### 8.3 `DstViewer`

AutoCAD Sheet Set 的 `.dst` 在本项目中按逐字节替换表编码。`DstViewer` 内置 256 字节的 `Encode` 和 `Decode` 查找表：

```text
DST 字节 -> Decode[字节] -> XML 字节 -> XmlDocument
XmlDocument.Save -> XML 字节 -> Encode[字节] -> DST 文件
```

这是简单可逆字节映射，不提供加密安全性、完整性校验或版本识别。四个方法的差别只是输入/输出是文件路径还是 `XmlDocument`。

主程序的关键调用为：

- `Functions.ps1`：`[UtilityClass.DstViewer]::DstToXml($dstfile)`。
- 主脚本：`[UtilityClass.DstViewer]::XmlToDst($xmldata, $dstfile)`。

修改替换表、XML 序列化方式或文件写入逻辑前，必须用现有 DST 做往返测试，并用 AutoCAD Sheet Set Manager 实际打开结果。当前方法不显式释放 `MemoryStream`，虽不持有外部文件句柄，仍建议用 `using` 规范生命周期。

## 9. 主程序集成和发布

### 9.1 集成边界

主程序只需要：

```text
Libs/AutoCad Utility.dll
Libs/UtilityClass.dll
```

重新构建并发布时：

1. 用 AutoCAD 2016 对应的托管 API 编译 `AutoCad Utility`。
2. 用最小 DWG 验证 `dellayouts`、`GetLayoutHandles`、`Ainsert`。
3. 将确认过的 DLL 复制到 `Libs/AutoCad Utility.dll`。
4. 构建 `UtilityClass`，用 DST 黄金样本做双向测试。
5. 将确认过的 DLL 复制到 `Libs/UtilityClass.dll`。
6. 记录程序集版本、文件哈希、AutoCAD 版本和验证样本。

`CoordinateDimension` 发布时还需要保证 `txtd.shx`、`hztxt.shx` 可被 AutoCAD 搜索到。`Transform` 发布时必须在 DLL 同目录提供与源码一致的 `config.ini`。

### 9.2 AutoCAD 版本升级

三个插件都直接引用 AutoCAD 2016 的托管程序集。升级 AutoCAD 时应：

1. 建立目标 AutoCAD 版本专用的引用路径。
2. 用目标 API 重新编译，保持 Autodesk 引用 `Copy Local=False`。
3. 检查 .NET Framework/.NET 运行时要求和 x64 设置。
4. 用命令级测试矩阵逐条验证，不能只验证 `NETLOAD` 成功。
5. 特别复核数据库事务、布局、字段、`DataTable` 和矩阵 API 的版本差异。

## 10. 测试建议

仓库目前没有自动化测试项目。建议按“纯逻辑单元测试 + AutoCAD 集成测试”分层补齐。

### 10.1 可直接单元测试的部分

- `SortToGroup`：空集合、整除、尾组、非法组大小。
- DST 编解码：固定 XML 往返、固定 DST 往返、缺失文件、非 XML 数据。
- 坐标文本格式和标注长度公式：从 `NodeDim` 抽离为不依赖 AutoCAD 的纯逻辑。
- 四参数计算：从 `Entity.TransformBy` 前抽离矩阵/点变换，用控制点验证正向、逆向和误差。
- Transform 配置解析：缺文件、缺节、无效数字、多参数选择和区域格式。

### 10.2 AutoCAD 集成测试矩阵

| 功能 | 最小样例 | 核对项 |
| --- | --- | --- |
| `dellayouts` | Model + 2 个图纸布局 | 只保留 Model，无异常 |
| `GetLayoutHandles` | 中文/英文/含空格布局名 | 文本路径、编码、行数、句柄可回查 |
| `Ainsert` | 2 个图纸布局 + 1 个签名 DWG | 每个图纸布局一个外参，模型空间没有，插入点为原点 |
| `BindXrefs` | 已加载、卸载、缺失外参组合 | 绑定/拆离结果和命令输出 |
| `FTT/FTTA` | DBText、MText、动态/静态属性块字段 | 转换范围及不可转换对象 |
| `clearxref` | 布局、模型和嵌套块中的同名外参 | 引用和定义均按预期删除 |
| `ZB/ZBH/ZBA` | WCS + 正负旋转 UCS，左右拖动 | 坐标值、方向、文字不倒置、实体数量 |
| `CoT/UCoT` | 已知控制点和多种实体 | 目标坐标、往返误差、失败时是否回滚 |
| DST | 现有可打开 DST | XML 往返后仍可打开，图纸/子集/属性完整 |

Core Console 主要覆盖 `AutoCad Utility` 的非交互命令；`CoordinateDimension` 和 `Transform` 的人工交互及图形视觉结果仍需桌面 AutoCAD 验收。

## 11. 已知问题与建议优先级

### P0：发布正确性和数据安全

1. 统一 `Transform` 的配置格式，把正确的 `config.ini` 纳入项目并复制到输出目录。
2. 为 `CoT/UCoT` 建立控制点和往返误差基线，明确两组默认参数的来源和坐标系方向。
3. 调整 `CoT/UCoT` 的部分提交语义，避免全图只转换一部分。
4. 为主程序依赖的 `dellayouts`、`GetLayoutHandles`、`Ainsert` 建立真实 DWG 回归样本。

### P1：可维护性和兼容性

1. 把 AutoCAD API 路径从个人 `.csproj.user` 迁移到可配置、可复现的构建属性。
2. 统一 Debug/Release 的 x64 目标。
3. 修复 `Ainsert` 每个布局重复 `AttachXref` 的实现，并验证行为不变。
4. 重构 `dellayouts` 的事务外 DBObject 使用。
5. 合并坐标标注三条命令和左右实体工厂的重复代码。
6. 统一 `RQBZ`/`RQZB` 名称，明确字体随包分发或安装前置条件。
7. 明确 `FTT/FTTA` 是否应支持静态属性块。

### P2：仓库卫生和现代化

1. 增加 `.gitignore`，清理 `.vs/bin/obj/debug.log` 和空 UI 草稿。
2. 删除未使用的模板资源和大量 Visual Studio 向导注释。
3. 用泛型集合、明确异常类型和结构化日志替代 `ArrayList`、宽泛捕获和模态弹窗。
4. 合并重复 INI 读取器，增加强类型配置与校验。
5. 增加统一解决方案、测试项目和可重复的构建脚本。

## 12. 常见修改入口

| 需求 | 修改入口 | 同步检查 |
| --- | --- | --- |
| 新增主流程 AutoCAD 命令 | `AutoCad Utility/myCommands.cs` | `CommandClass`、PowerShell `.scr`、Core Console 兼容性 |
| 修改布局句柄文件格式 | `GetLayoutHandles.ListLayouts` | PowerShell 解析逻辑和 DST 布局关联 |
| 修改签名外参插入方式 | `Ainsert.MyCommand` | 单/多布局、图层 0、外参定义命名和主脚本调用 |
| 增加标注内容 | `NodeDim` + `CreateDim*` | 左右布局、长度公式、三种命令和 UCS |
| 修改标注字高/参数 | `GCLZBConfig` DataTable | 既有 DWG 配置兼容和默认迁移 |
| 修改坐标转换参数 | `Transform/myCommands.cs` + `config.ini` | 正反向公式、控制点和全图回滚 |
| 修改 DST 格式 | `UtilityClass.DstViewer` | 现有 DST 往返和 AutoCAD 实际打开 |
| 升级 AutoCAD | 三个 AutoCAD `.csproj` | API 引用、运行时、x64、所有命令回归 |

接手开发时，建议先固定 AutoCAD 版本和黄金 DWG/DST 样本，再处理 P0 项；当前最危险的区域不是编译，而是坐标变换的参数契约和破坏性命令的运行时结果。
