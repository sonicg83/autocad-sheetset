# UtilityClass DST/XML 转换实现分析

## 1. 文档目的

本文分析 `UtilityClass.DstViewer` 在 AutoCAD Sheet Set（`.dst`）与 XML 之间的双向转换实现，说明它在项目中的调用边界、字节转换算法、XML 序列化行为、异常与性能特征，并给出后续维护和重构时应保留的兼容性要求。

分析依据包括：

- [`plugin/UtilityClass/Class1.cs`](../plugin/UtilityClass/Class1.cs) 中的实现源码；
- [`plugin/UtilityClass/UtilityClass.csproj`](../plugin/UtilityClass/UtilityClass.csproj) 中的构建目标；
- [`Functions.ps1`](../Functions.ps1) 中的 DST 读取和 XML 查询逻辑；
- [`图纸集生成-市政用0.24.ps1`](../图纸集生成-市政用0.24.ps1) 中的 XML 模板组装和 DST 输出逻辑；
- 当前仓库内实际分发 DLL 的反射和查表一致性验证。

本文只讨论仓库内已有实现。仓库目前没有可用于自动验证的 `.dst` 黄金样本，因此本文不能替代 AutoCAD Sheet Set Manager 的实际打开测试。

## 2. 核心结论

`UtilityClass` 的 DST/XML 转换不是对象序列化、压缩或密码学加密，而是以下两步组合：

1. 使用 `XmlDocument` 在 XML DOM 和 XML 字节流之间转换；
2. 使用固定的 256 项查找表，对字节流逐字节进行一一替换。

整体流程如下：

```text
XmlDocument
    │ XmlDocument.Save
    ▼
XML 字节数组
    │ Encode[XML字节]
    ▼
DST 字节数组
    │ File.WriteAllBytes
    ▼
.dst 文件
```

反向流程为：

```text
.dst 文件
    │ File.ReadAllBytes
    ▼
DST 字节数组
    │ Decode[DST字节]
    ▼
XML 字节数组
    │ XmlDocument.Load
    ▼
XmlDocument
```

`DstViewer` 不理解以下业务内容：

- `AcSmDatabase`、`AcSmSheetSet`、`AcSmSubset`、`AcSmSheet` 等节点含义；
- `clsid`、`ID`、`propname`、`vt` 等属性含义；
- GUID 是否唯一；
- 布局句柄是否有效；
- DWG 文件是否存在；
- XML 是否符合特定 AutoCAD 版本的 Sheet Set 数据模型。

这些业务结构由 PowerShell 脚本组装和解释，`UtilityClass` 只负责 XML 字节与 DST 字节之间的可逆转换。

## 3. 项目集成边界

### 3.1 构建和加载方式

`UtilityClass` 的构建目标是：

```text
.NET Framework 4.8
AnyCPU
Library
```

它不依赖 AutoCAD 托管 API，而是由 Windows PowerShell 5.1 进程直接加载：

```powershell
Add-Type -Path "$PSScriptRoot\Libs\UtilityClass.dll"
```

因此它与 AutoCAD 插件 DLL 的运行边界不同：

```text
Windows PowerShell 5.1
    └─ 加载 UtilityClass.dll
        ├─ 读取 DST
        └─ 写入 DST

AutoCAD / Core Console
    └─ 消费生成后的 DWG 和 DST
```

不能在没有兼容性安排的情况下把当前 `UtilityClass.dll` 直接替换为只支持现代 .NET 的程序集，否则 Windows PowerShell 5.1 将无法加载它。

### 3.2 当前 DLL 一致性

仓库内以下两个 DLL 的 SHA-256 完全一致：

```text
Libs/UtilityClass.dll
plugin/UtilityClass/bin/Debug/UtilityClass.dll
```

哈希为：

```text
43EBABF8FFA0E52A260511A2E294EC55AD7B6F47293CD3ACD0C7AE9E87E13DAE
```

程序集版本为 `1.0.0.0`。通过反射确认，实际 DLL 暴露的四个公共方法与当前源码一致。

## 4. 字节替换算法

### 4.1 Encode 和 Decode 表

`DstViewer` 内部定义两个长度为 256 的静态只读字节数组：

- `Encode`：XML 字节到 DST 字节的映射；
- `Decode`：DST 字节到 XML 字节的映射。

私有转换方法为：

```csharp
private static byte[] DecryptFile(IEnumerable<byte> bytes)
{
    return bytes.Select(b => Decode[b]).ToArray();
}

private static byte[] EncryptFile(IEnumerable<byte> bytes)
{
    return bytes.Select(b => Encode[b]).ToArray();
}
```

如果 XML 中某个字节的无符号值为 `x`，写入 DST 时执行：

```text
dstByte = Encode[x]
```

读取 DST 时执行：

```text
xmlByte = Decode[dstByte]
```

字节值天然位于 `0～255`，因此可以安全作为数组索引。

### 4.2 可逆性

对当前实际 DLL 中的查找表进行了完整验证：

- `Encode.Length == 256`；
- `Decode.Length == 256`；
- 两张表各自都包含 256 个不同值；
- 对所有 `x ∈ [0,255]`，`Decode[Encode[x]] == x`；
- 对所有 `x ∈ [0,255]`，`Encode[Decode[x]] == x`。

这说明两张表互为逆置换。转换具有以下性质：

- 一个输入字节严格对应一个输出字节；
- 转换前后字节数组长度相同；
- 算法时间复杂度为 `O(n)`；
- 不依赖文本编码，可以处理 UTF-8、UTF-16 或其他合法 XML 编码产生的任意字节；
- `Encode` 和 `Decode` 不能混用，它们不是同一张对称表。

### 4.3 字节示例

带 UTF-8 声明的 `XmlDocument` 在当前本机运行时保存到流后，以以下字节开头：

```text
EF BB BF 3C 3F 78 6D 6C ...
```

其中前三个字节是 UTF-8 BOM，后续是 `<?xml`。经过 `Encode` 表后，对应 DST 字节为：

```text
9D 51 4D D0 CD 14 E3 E0 ...
```

读取时对后一组字节执行 `Decode`，会恢复前一组 XML 字节。

### 4.4 不是安全加密

尽管源码使用了 `EncryptFile` 和 `DecryptFile` 作为方法名，该算法不具备密码学安全性：

- 替换表固定写在 DLL 中；
- 没有密钥；
- 没有随机数或初始化向量；
- 相同 XML 字节永远生成相同 DST 字节；
- 没有完整性校验或身份验证；
- 查表关系可以直接从 DLL 或源码恢复。

因此更准确的术语是“编码/解码”或“字节混淆/还原”。

## 5. 四个公共接口

| 方法 | 输入 | 输出 | 主要用途 |
| --- | --- | --- | --- |
| `DstToXmlFile` | DST 文件路径、XML 文件路径 | XML 文件 | 把 DST 解码、解析并重新保存为 XML 文件 |
| `DstToXml` | DST 文件路径 | `XmlDocument` | 供 PowerShell 通过 XPath 查询 DST 内容 |
| `XmlFileToDst` | XML 文件路径、DST 文件路径 | DST 文件 | 把现有 XML 文件解析、重新序列化并编码为 DST |
| `XmlToDst` | `XmlDocument`、DST 文件路径 | DST 文件 | 把脚本动态组装的 DOM 输出为 DST |

### 5.1 `DstToXmlFile`

执行顺序：

1. 使用 `File.Exists(dstfile)` 检查输入文件；
2. 使用 `File.ReadAllBytes` 读取全部 DST 字节；
3. 使用 `Decode` 表解码；
4. 使用 `XmlDocument.Load` 解析解码后的 XML；
5. 使用 `XmlDocument.Save(xmlfile)` 重新保存 XML。

它不是简单地把解码后的原始 XML 字节直接写入文件。因为中间经过 DOM 解析和重新保存，所以输出 XML 的缩进、换行、BOM 和其他词法表现可能发生变化。

### 5.2 `DstToXml`

前四步与 `DstToXmlFile` 相同，但最终直接返回 `XmlDocument`。

项目中的读取流程为：

```text
DST
  ↓ UtilityClass.DstViewer.DstToXml
XmlDocument
  ↓ Functions.ps1 中的 XPath
图纸集属性、图纸属性、布局信息
```

例如 `Functions.ps1` 会读取：

- `/AcSmDatabase/AcSmSheetSet/AcSmCustomPropertyBag/AcSmCustomPropertyValue`；
- `//AcSmSheet`；
- `AcSmProp[@propname='Title']`；
- `AcSmAcDbLayoutReference/AcSmProp[@propname='FileName']`。

这些 XPath 和 `Flags=1/2` 的业务解释都不属于 `UtilityClass`。

### 5.3 `XmlFileToDst`

执行顺序：

1. 使用 `File.Exists(xmlfile)` 检查 XML 输入文件；
2. 使用 `XmlDocument.Load(xmlfile)` 解析 XML；
3. 使用 `XmlDocument.Save(MemoryStream)` 重新序列化；
4. 使用 `Encode` 表编码全部 XML 字节；
5. 使用 `File.WriteAllBytes` 写入 DST。

它不会保留 XML 文件的原始字节形式。即使 XML 节点语义不变，输出 DST 也可能因为缩进、换行、BOM 或编码发生变化。

### 5.4 `XmlToDst`

这是当前主程序生成 DST 时使用的方法：

1. 接收脚本已经组装好的 `XmlDocument`；
2. 将 DOM 保存到 `MemoryStream`；
3. 取得序列化后的完整字节数组；
4. 使用 `Encode` 表逐字节编码；
5. 覆盖写入目标 DST 文件。

它不会检查 XML 是否符合 AutoCAD Sheet Set 规范。只要 `XmlDocument.Save` 成功，就会尝试生成 DST 文件。

## 6. XML 结构由 PowerShell 负责

主脚本中的基础模板声明了：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<AcSmDatabase ...>
  <AcSmProp propname="DbVersion" vt="8">1.1</AcSmProp>
  <AcSmSheetSet ...>
    ...
  </AcSmSheetSet>
</AcSmDatabase>
```

随后，`Functions.ps1` 中的 `CreateMain`、`CreateSub` 和 `UpdateValue` 负责操作 DOM：

- `CreateMain` 创建包含 `clsid`、`ID`、`propname`、`vt` 的对象节点；
- `CreateSub` 创建包含 `propname`、`vt` 和文本值的属性节点；
- `UpdateValue` 通过 XPath 更新现有节点文本。

主脚本进一步创建：

- 图纸集自定义属性；
- 图纸自定义属性；
- 子集；
- 图纸；
- DWG 布局引用；
- 文件相对路径；
- 图纸编号和标题。

因此职责划分应理解为：

| 层次 | 职责 |
| --- | --- |
| 主 PowerShell 脚本 | 从 Excel、DWG 和配置中生成图纸集业务数据 |
| `Functions.ps1` XML 帮助函数 | 创建节点、设置属性和更新值 |
| `XmlDocument` | 保证 XML 语法、编码文本和转义特殊字符 |
| `UtilityClass.DstViewer` | XML 字节与 DST 字节之间的可逆替换 |
| AutoCAD Sheet Set Manager | 最终解释和验证 Sheet Set 业务结构 |

## 7. XML 序列化行为

### 7.1 默认不保留格式空白

`DstViewer` 创建 `XmlDocument` 后没有设置 `PreserveWhitespace`，其默认值为 `false`。

这意味着加载 XML 时，非必要的缩进和空白节点可能被丢弃；再次保存时，`XmlDocument` 会重新生成格式。例如：

```xml
<root>  <a>1</a>

  <b>2</b></root>
```

可能被重新保存为：

```xml
<root>
  <a>1</a>
  <b>2</b>
</root>
```

因此当前实现主要保证 XML DOM 语义可恢复，不保证原始 XML 文本或原始 DST 字节完全一致。

### 7.2 编码和 BOM 会进入 DST

`XmlDocument.Save(Stream)` 的输出编码会受到 XML 声明影响。在当前本机运行时验证到：

| XML 状态 | 保存结果 |
| --- | --- |
| 声明 `encoding="UTF-8"` | UTF-8，包含 BOM |
| 声明 `encoding="UTF-16"` | UTF-16，包含对应 BOM |
| 没有 XML 声明 | UTF-8，无 XML 声明和 BOM |

这些 BOM、声明、缩进和换行本身也是 XML 字节的一部分，会被 `Encode` 表处理。因此更改 XML 序列化配置会直接改变生成的 DST 字节。

### 7.3 往返一致性的层次

需要区分三种不同的一致性：

1. **字节映射一致性**：单独执行 `Encode` 后再执行 `Decode`，可以恢复完全相同的字节，当前已验证。
2. **XML 语义一致性**：经过 `XmlDocument.Load` 和 `Save` 后，元素、属性和值通常保持一致。
3. **DST 字节一致性**：DST 解码成 DOM、再从 DOM 生成 DST 后，不保证与原始 DST 逐字节相同。

AutoCAD 是否接受语义相同但字节不同的 DST，必须使用实际 Sheet Set Manager 验证。

## 8. 异常和边界行为

### 8.1 输入文件不存在

`DstToXmlFile`、`DstToXml` 和 `XmlFileToDst` 会主动检查输入文件，但只抛出无路径信息的：

```csharp
throw new FileNotFoundException();
```

调用者无法直接从异常消息确认缺失的是哪个文件。

### 8.2 环境变量路径处理不一致

DST 读取方法的逻辑为：

```csharp
File.Exists(dstfile)
File.ReadAllBytes(Environment.ExpandEnvironmentVariables(dstfile))
```

文件存在性检查使用原始路径，实际读取却使用环境变量展开后的路径。因此传入 `%TEMP%\example.dst` 时，文件即使存在，也可能在检查阶段被错误判定为不存在。

XML 输入路径和所有输出路径没有环境变量展开，四个接口的路径契约并不一致。

### 8.3 XML 语法错误

如果 DST 解码后不是合法 XML，`XmlDocument.Load` 会抛出 `XmlException`。代码没有：

- DST 文件头判断；
- 版本判断；
- 解码前长度检查；
- XML Schema 校验；
- 自定义错误包装。

因此 XML 解析器实际上承担了主要的输入有效性检查。

### 8.4 输出文件行为

`File.WriteAllBytes` 会直接创建或覆盖目标文件：

- 不会自动创建父目录；
- 不会备份已有 DST；
- 不使用临时文件和原子替换；
- 不处理两个任务同时写入同一目标的问题；
- 写入中断时可能留下不完整文件。

### 8.5 空参数

代码没有显式校验空字符串或 `null`：

- `XmlToDst(null, path)` 会在 `xml.Save` 处产生空引用异常；
- 无效路径可能被 `File.Exists` 转换为简单的“不存在”；
- 空输出路径和非法目录由底层文件 API 抛出异常。

## 9. 性能和资源使用

算法本身是线性复杂度，但不是流式转换。

DST 到 XML 时大致同时存在：

```text
原始 DST 字节数组
解码后的 XML 字节数组
MemoryStream 对解码数组的引用
XmlDocument DOM
```

XML 到 DST 时大致存在：

```text
XmlDocument DOM
MemoryStream 内部缓冲区
MemoryStream.ToArray 产生的 XML 字节副本
Encode + ToArray 产生的 DST 字节数组
```

另外，LINQ `Select` 会对每个字节产生枚举和委托调用开销。对一般 Sheet Set 文件而言通常可以接受，但如果以后处理大型 DST，可以改为固定长度数组和普通循环，或者设计流式查表转换。

四个方法中的 `MemoryStream` 均未通过 `using` 显式释放。`MemoryStream` 不持有外部文件句柄，因此风险较低，但仍建议规范生命周期。

## 10. 安全性和完整性风险

### 10.1 无防篡改能力

查表算法没有校验和或认证标签。DST 中任意字节被修改后，会确定性地解码成另一个 XML 字节：

- 如果结果破坏 XML 语法，会在解析时失败；
- 如果结果仍是合法 XML，错误数据可能被静默接受；
- 代码无法判断文件是正常修改、意外损坏还是恶意篡改。

### 10.2 XML 加载策略不显式

代码使用默认 `XmlDocument.Load`，没有显式设置 DTD、外部实体和文档大小限制。实际行为依赖运行时默认值。

如果允许读取不可信 DST，建议通过配置明确的 `XmlReaderSettings` 加载，并设置适当的字符数和实体展开上限。

### 10.3 没有业务结构校验

生成 DST 前不会检查：

- 根元素和 `DbVersion`；
- 必需节点；
- GUID 格式和唯一性；
- `clsid` 与节点类型的匹配关系；
- `vt` 与属性值的类型关系；
- `Flags` 的允许值；
- 引用文件和布局句柄。

这些错误只能在后续 PowerShell 查询或 AutoCAD 打开时暴露。

## 11. 主要维护风险

按优先级整理如下：

| 优先级 | 风险 | 影响 |
| --- | --- | --- |
| 高 | 没有 DST 黄金样本和 AutoCAD 打开测试 | 修改后可能生成语法正确但 AutoCAD 不接受的 DST |
| 高 | 直接覆盖目标文件 | 写入失败可能破坏已有图纸集 |
| 高 | 没有业务 Schema/版本校验 | 无效结构直到 AutoCAD 打开时才暴露 |
| 中 | XML 重新序列化改变 BOM、空白和换行 | DST 字节往返不稳定，兼容性难以判断 |
| 中 | 环境变量路径检查与读取不一致 | 合法路径可能被误判为不存在 |
| 中 | 异常缺少文件路径和操作上下文 | PowerShell 侧难以定位故障 |
| 低 | 非流式、存在多份字节副本 | 大型 DST 会增加内存和 CPU 开销 |
| 低 | `MemoryStream` 未显式释放 | 代码规范和可维护性较差 |

## 12. 推荐的重构方向

### 12.1 第一阶段：只增强保护，不改变格式

在保持查找表和 XML 序列化行为不变的前提下：

1. 校验 `null`、空路径和父目录；
2. 统一进行 `Environment.ExpandEnvironmentVariables` 和绝对路径解析；
3. 在异常中包含输入和输出路径；
4. 使用 `using` 管理流；
5. 先写临时文件，再原子替换目标 DST；
6. 对根节点和 `DbVersion` 做最小校验；
7. 为读取 XML 配置明确的安全限制。

### 12.2 第二阶段：建立序列化契约

明确并固定以下项目：

- XML 编码；
- 是否写 BOM；
- 是否写 XML 声明；
- 换行符；
- 是否缩进；
- 属性和节点顺序；
- 空元素使用 `<node />` 还是 `<node></node>`；
- 是否保留输入空白。

在没有黄金样本前，不建议直接改变这些行为。

### 12.3 第三阶段：流式和跨运行时实现

如果以后需要为现代 .NET 或 Python 重写，可以把查表算法独立为无状态模块：

```text
IDstByteCodec
    ├─ Encode(ReadOnlySpan<byte>)
    └─ Decode(ReadOnlySpan<byte>)
```

XML Schema 组装、XML 序列化和字节编码应拆成不同层次，避免继续把三种职责混合在一个静态类中。

## 13. 建议测试矩阵

### 13.1 字节算法测试

- 验证两张表长度都是 256；
- 验证每张表都没有重复值；
- 遍历全部 256 个字节验证双向可逆；
- 验证编码前后长度相同；
- 使用已知 XML 头验证固定 DST 字节结果。

### 13.2 XML 序列化测试

- UTF-8 带 BOM；
- UTF-8 不带 BOM；
- UTF-16；
- 无 XML 声明；
- 中文、Emoji 和其他非 ASCII 字符；
- `&`、`<`、`>`、单双引号；
- 空元素、CDATA、注释和处理指令；
- 格式空白和文本内有效空格。

### 13.3 文件和异常测试

- 输入文件不存在；
- 环境变量路径；
- 相对路径和绝对路径；
- 输出目录不存在；
- 目标文件只读或被占用；
- 两个任务同时写入同一 DST；
- 空文件、截断文件和随机字节文件；
- 解码后合法 XML、但不是 `AcSmDatabase` 的文件。

### 13.4 AutoCAD 集成测试

必须准备至少一个经过人工确认的 DST 黄金样本，并验证：

1. 黄金 DST 可以解码为预期 XML；
2. XML 重新编码后的 DST 可以被 AutoCAD 打开；
3. 图纸集名称、子集、图纸编号和标题正确；
4. 自定义属性和 `Flags` 作用域正确；
5. DWG 布局引用和相对路径正确；
6. AutoCAD 保存后再次读取，业务数据没有丢失；
7. 在目标支持的 AutoCAD 版本上分别验证。

## 14. 最终评价

当前实现的优点是简单、无 AutoCAD API 依赖、查表过程完全可逆，而且已经稳定集成在 Windows PowerShell 主流程中。它适合作为一个轻量的 DST 字节编解码适配器。

主要问题不在查表算法本身，而在其周围缺少明确契约：

- XML 会被重新序列化，但序列化格式没有测试固定；
- 没有 DST 完整性和业务结构校验；
- 文件覆盖不是原子操作；
- 路径和异常行为不一致；
- 缺少黄金样本与 AutoCAD 自动/人工回归流程。

后续修改时，最重要的原则是先建立黄金样本和 AutoCAD 打开测试，再调整查找表、XML 序列化或文件写入方式。仅验证“生成了 `.dst` 文件”不足以证明转换兼容。
