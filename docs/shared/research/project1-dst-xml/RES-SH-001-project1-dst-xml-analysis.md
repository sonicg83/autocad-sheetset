---
id: RES-SH-001
title: Project1 DST/XML 结构分析
status: accepted
owners: [shared]
created: 2026-08-11
updated: 2026-08-17
---

# project1 DST/XML 结构分析

## 1. 目的与产物

本文记录对本地样本 `sample/project1/图纸集数据文件.dst` 的只读分析结果。解码使用本项目的 `DstCodec`：它以固定的 256 项查找表逐字节将 DST 还原为 XML，并通过 `lxml` 验证 XML 语法。该过程不使用 AutoCAD COM 或 Core Console，也不改写原始 DST、DWG 或样本目录。

同目录交付物如下：

| 文件 | 内容 | 编码/规模 |
| --- | --- | --- |
| `project1_sheetset.xml` | DST 直接解码所得的完整 AcSm XML | UTF-8，845,628 字节 |
| `project1_sheet_manifest.csv` | 每张图纸、所属子集、DWG、布局和自定义属性清单 | UTF-8 with BOM，298 行 |
| `RES-SH-001-project1-dst-xml-analysis.md` | 本分析文档 | UTF-8 |

XML 是解码后的原始字节结果，不经过序列化、格式化或结构编辑，因此与源 DST 的一一字节置换关系仍成立。CSV 仅是 XML 中受控业务字段的投影，不能用于重建 DST。

## 2. 解码与完整性结果

| 项目 | 结果 |
| --- | --- |
| DST 大小 | 845,628 字节 |
| 解码 XML 大小 | 845,628 字节 |
| XML 声明 | `version="1.0" encoding="UTF-8"` |
| XML 根元素 | `AcSmDatabase` |
| `DbVersion` | `1.1` |
| 含 `ID` 的对象数 | 3,125 |
| 唯一 `ID` 数 | 3,125 |
| 项目 `AcsmDocument.validate()` 问题数 | 0 |

DST 格式在本项目中的含义是 XML 字节的固定置换，而不是压缩格式或加密格式。因此 DST 与 XML 必然等长；但若把 XML 解析后重新序列化，空白、声明、BOM 和属性表现可能改变，重新编码得到的 DST 不保证逐字节等于原文件。

## 3. 文档树

```text
AcSmDatabase
├─ AcSmProp: DbFingerPrint / DbVersion / FileRevision
└─ AcSmSheetSet
   ├─ 基本属性：Desc / Name / PromptForDwt
   ├─ 图纸集自定义属性袋：41 项
   ├─ 45 × AcSmSubset
   │  └─ 298 × AcSmSheet
   │     ├─ Number、Title
   │     ├─ 图纸自定义属性袋：每张 6 项
   │     ├─ AcSmAcDbLayoutReference
   │     └─ AcSmSheetViews
   ├─ DefDwtLayout / DefLabelBlk / NewSheetLocation
   ├─ CalloutBlocks / ProjectPointLocations
   ├─ PublishOptions / Resources
   ├─ SheetSelSets
   └─ ViewCategories
```

样本的 45 个 `AcSmSubset` 全部直属 `AcSmSheetSet`，不存在嵌套子集。图纸编号覆盖 `0000` 至 `0296`；其中编号 `0000` 存在封面和扉页两张，故总数为 298，而不是 297。

## 4. 节点统计与语义

| 节点 | 数量 | 在样本中的作用 |
| --- | ---: | --- |
| `AcSmDatabase` | 1 | Sheet Set 数据库根，包含版本、修订和图纸集对象。 |
| `AcSmSheetSet` | 1 | 图纸集主体及项目级元数据。 |
| `AcSmSubset` | 45 | 图纸分组；例如封面、目录、设备表、平面图和各井段大样图。 |
| `AcSmSheet` | 298 | 单张图纸，保存图号、标题、属性及布局引用。 |
| `AcSmAcDbLayoutReference` | 299 | 298 个图纸布局引用，外加 1 个空的 `DefDwtLayout` 默认模板布局。 |
| `AcSmFileReference` | 46 | 文件或目录引用，例如 `NewSheetLocation` 及资源引用。 |
| `AcSmCustomPropertyBag` | 299 | 图纸集 1 个，加上每张图纸各 1 个。 |
| `AcSmCustomPropertyValue` | 1,829 | 图纸集 41 项，加上 298 张图纸 × 6 项。 |
| `AcSmSheetViews` | 298 | 每张图纸均保留的视图容器。 |
| `AcSmProp` | 5,377 | 标量字段统一以该节点表达。 |

对象节点普遍具有下列属性：

```xml
<AcSmSheet clsid="g..." ID="g..." propname="Sheet" vt="13">
```

- `ID`：AcSm 对象身份。样本中唯一；它不是 DWG Handle。
- `clsid`：AutoCAD AcSm 对象类别标识。相同 XML 元素在样本中使用同一类标识。
- `propname`：该对象作为父对象属性时的名称，例如 `Sheet`、`Layout` 或 `DefDwtLayout`。
- `vt`：持久化类型标记。普通文本属性主要使用 `vt="8"`；不要仅凭显示值替换或擅自变更该标记。

`AcSmProp` 是常规标量属性的统一表示，例如：

```xml
<AcSmProp propname="Number" vt="8">0296</AcSmProp>
<AcSmProp propname="Title" vt="8">...</AcSmProp>
```

## 5. 图纸、DWG 与布局绑定

每个 `AcSmSheet` 恰好拥有一个 `AcSmAcDbLayoutReference`，项目校验已确认 298 张图纸均满足此约束。典型结构如下：

```xml
<AcSmAcDbLayoutReference propname="Layout" ...>
  <AcSmProp propname="AcDbHandle" vt="8">21DEB2</AcSmProp>
  <AcSmProp propname="FileName" vt="8">C:\test\...dwg</AcSmProp>
  <AcSmProp propname="Name" vt="8">0296 ...</AcSmProp>
  <AcSmProp propname="Relative_FileName" vt="8">.\...dwg</AcSmProp>
</AcSmAcDbLayoutReference>
```

| 字段 | 含义 | 样本状态 |
| --- | --- | --- |
| `FileName` | 创建该图纸集机器中的绝对 DWG 路径 | 298 条均以失效的 `C:\test\` 为根。 |
| `Relative_FileName` | 相对于 DST 文件目录的 DWG 路径 | 298 条均为 `.\文件名.dwg`。 |
| `Name` | DWG 内布局名称 | 每张图纸对应一个布局名。 |
| `AcDbHandle` | DWG 数据库中布局的 Handle | 不能与 XML `ID` 混用。 |

298 张图纸共引用 45 个不同的 DWG；目录中存在 53 个 DWG。其中被 DST 引用的 45 个文件均能根据 `Relative_FileName` 在样本目录解析到。另有 8 个未被 DST 引用的 DWG：7 个电子签名文件与 1 个冲突副本。路径重定位应优先使用 `Relative_FileName`，只有无法解析时才考虑原始绝对路径或人工指定根目录。

## 6. 自定义属性

图纸集的 `AcSmCustomPropertyBag` 含 41 项项目元数据，包括工程/专业标识、设计阶段、出图年月、单位、人员和图名相关字段。图纸级属性的模式完全一致，每张均有：

```text
备注、出图比例、设计人、图幅、校对人、专业负责人
```

图纸自定义属性不是 XML 属性，而是一个对象及其两个标量属性：

```xml
<AcSmCustomPropertyValue propname="图幅" ...>
  <AcSmProp propname="Flags" vt="3">...</AcSmProp>
  <AcSmProp propname="Value" vt="8">A2</AcSmProp>
</AcSmCustomPropertyValue>
```

样本中 `图幅` 全部为 `A2`，`备注` 全为空。CSV 已将六个图纸级自定义属性展开为列；项目级属性不在 CSV 中展开，以避免重复 298 次。

## 7. 其他图纸集配置

- `DefDwtLayout`：默认 DWT 布局占位对象；本样本没有把它作为普通图纸布局使用。
- `DefLabelBlk`：默认标签块引用。
- `NewSheetLocation`：新图纸默认位置；其绝对路径同样是旧的 `C:\test`，相对路径为当前目录。
- `PublishOptions`：发布配置；含 `DwfType` 与 `PromptForName`。
- `CalloutBlocks`、`ProjectPointLocations`、`Resources`、`SheetSelSets`、`ViewCategories`：由 Sheet Set Manager 管理的辅助对象，即便当前为空或未在业务界面展示，也应在写回时原样保留。

## 8. 安全修改准则

1. 不要通过字符串替换修改 XML；使用 DOM 定位受控对象与 `AcSmProp`。
2. 不要删除未知节点、未知属性、`clsid`、`vt`、`Flags` 或改变无关兄弟节点顺序。
3. 编辑图纸时必须保留 `Number`、`Title` 和唯一的 `AcSmAcDbLayoutReference`；后者的四个必填字段应同步校验。
4. 迁移目录时，同时更新 `FileName` 与 `Relative_FileName`，并通过实际 DWG 文件与布局 Handle 回读验证。
5. 创建对象时生成新的 AcSm `ID`；移动图纸时保留既有图纸及其布局对象 ID。
6. 写入 DST 时通过现有暂存、校验、发布与回滚流程，不直接覆盖源文件。

项目中 DST 编解码实现见 `src/dst_manager/infrastructure/dst_codec/codec.py`，AcSm DOM 的受控投影与验证见 `src/dst_manager/infrastructure/acsm_xml/document.py`。

## 9. 验证记录

- 以 `DstCodec.decode_file()` 解码源 DST；`lxml` 成功解析。
- 使用 `AcsmDocument.validate()` 验证，结果为 0 项问题。
- 执行 `uv run pytest tests/unit/test_core.py -q`，结果为 5 passed。
- 本次仅导出文档、XML 和 CSV；未修改样本目录、DST 或 DWG。
