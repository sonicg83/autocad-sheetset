---
id: PLAN-DM-006
title: v0.21 受控图纸集编辑实施计划
status: proposed
owners:
  - dst-manager
created: 2026-08-21
updated: 2026-08-21
related:
  - SPEC-DM-001
  - ARCH-DM-001
---

# v0.21 受控图纸集编辑实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项实施；步骤使用复选框跟踪。

**目标：** 实现 `SPEC-DM-001` 定义的属性定义维护、CSV、受控插入子集/图纸、统一标题派生，并移除与其冲突的旧编辑入口。

**架构：** 在领域层新增纯函数的编辑规则与最终结构派生器，所有结构命令先产生完整计划，再由 AcSm DOM 适配器和 CAD 任务消费同一计划。属性定义以受控 DOM 操作实现，CSV 只转换成相同的领域命令；API 和 Vue 仅组装、预览和提交命令，不复制最终校验规则。

**技术栈：** Python 3.12、pytest、lxml、FastAPI、Pydantic Settings、Vue 3、TypeScript、Vite、Playwright、AutoCAD 2016/2020 Core Console。

**规范：** [`SPEC-DM-001`](../../../../docs/dst-manager/specs/SPEC-DM-001-v021-sheetset-editing-adjustment.md)

## 全局约束

- 目标系统为 Windows 11；Python 不低于 3.12，依赖使用 `uv` 管理；Web 仅在 `web/` 中使用 npm。
- DST 写入必须保持 `DST → XML DOM → DST`，保留未知节点、属性、顺序和文本；不得字符串替换 XML。
- 所有用户输入都必须通过既有危险名称、SCR 参数和路径校验；不得拼接为 SCR、Shell 或文件操作。
- 只读打开绝不创建 `.dst-manager/`、不改写 DST/DWG、也不更新时间戳。
- 正式写入必须使用永久 before 快照、暂存、校验、可恢复整批发布；失败必须恢复整批发布前状态。
- Web 只监听 `127.0.0.1`；CAD 操作只使用固定命令、固定 SCR 渲染器及匹配版本 Worker。
- 任何改动都更新根目录 `changelog.md`；计划完成前不得标记为 `completed`。
- 每项任务先写失败测试，最小实现后运行相关测试；交付前运行 Ruff、相关 pytest、Web build 和 Playwright。真实 CAD 测试只在显式启用的临时副本执行。

## 文件结构

| 文件 | 责任 |
| --- | --- |
| `docs/dst-manager/adr/ADR-DM-001-controlled-sheetset-editing.md` | 记录由自由编辑切换到受控插入/派生模型的决策及替代关系。 |
| `src/dst_manager/config.py`、`.env.example` | 读取和校验标题后缀配置。 |
| `src/dst_manager/domain/editing.py`（新建） | 属性名规范化、CSV 行校验、标题后缀、图号范围、全局编号和插入位置的无副作用规则。 |
| `src/dst_manager/domain/models.py`、`src/dst_manager/domain/planning.py` | 表达子集可编辑标题/派生范围，并由最终结构生成 CAD/DST 执行计划。 |
| `src/dst_manager/infrastructure/acsm_xml/document.py` | 投影属性定义并受控创建/删除属性、子集和图纸 DOM 节点。 |
| `src/dst_manager/application/service.py`、`src/dst_manager/application/cad_job.py` | 预览/执行新命令，生成 CSV 差异，发布新建或重建 DWG。 |
| `src/dst_manager/interfaces/api.py`、`src/dst_manager/interfaces/serialization.py` | 暴露 CSV 模板、导入/导出及派生字段；删除旧命令入口。 |
| `web/src/App.vue`、`web/tests/e2e/main.spec.ts` | 替换旧编辑控件，展示属性、CSV、受控插入和可审阅预览。 |
| `tests/unit/test_v021_editing.py`（新建）、`tests/unit/test_acsm_custom_properties.py`、`tests/unit/test_core.py`、`tests/integration/test_api.py` | 覆盖领域规则、DOM 受控写入、计划、API 和只读/发布回归。 |

---

### 任务 1：记录替代决策并建立标题后缀配置

**文件：**

- Create: `docs/dst-manager/adr/ADR-DM-001-controlled-sheetset-editing.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `src/dst_manager/config.py`
- Modify: `.env.example`
- Create: `tests/unit/test_config.py`

**接口：**

- 产出 `Settings.enable_add_number_suffix: bool` 和 `Settings.number_suffix_type: Literal[1, 2]`。
- `domain/editing.py` 只能读取上述已校验字段，不能自行读取环境变量。

- [ ] **步骤 1：写配置与决策的失败测试**

```python
def test_suffix_settings_use_spec_defaults(monkeypatch):
    monkeypatch.delenv("EnableAddNumberSuffix", raising=False)
    monkeypatch.delenv("NumberSuffixType", raising=False)
    settings = Settings(_env_file=None)
    assert settings.enable_add_number_suffix is True
    assert settings.number_suffix_type == 1


def test_suffix_settings_reject_invalid_values(monkeypatch):
    monkeypatch.setenv("NumberSuffixType", "3")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
```

- [ ] **步骤 2：运行失败测试确认当前配置没有该契约**

运行：`uv run pytest tests/unit/test_config.py -q`  
预期：失败，提示 `Settings` 缺少后缀字段或非法值未被拒绝。

- [ ] **步骤 3：最小实现配置与 ADR**

在 `Settings` 中使用不带 `DST_MANAGER_` 前缀的 `validation_alias`，以精确匹配规范约定的 `.env` 名称；值类型使用严格布尔和 `Literal[1, 2]`。在 `.env.example` 补充：

```dotenv
# 是否自动添加图纸标题序号后缀，默认 true
EnableAddNumberSuffix=true
# 1=汉字序号，2=数字序号，默认 1
NumberSuffixType=1
```

ADR 必须说明：移除 `move_sheet`、`reorder_sheet`、子集排序和手工图纸标题编辑；以位置插入、派生标题和完整预览替代；`ARCH-DM-001` 的事务与 Worker 决策不变。更新 DST Manager README，列出 ADR。

- [ ] **步骤 4：运行配置与文档链接检查**

运行：`uv run pytest tests/unit/test_config.py -q`  
预期：通过；README 中 ADR 链接可解析。

- [ ] **步骤 5：提交该独立变更**

```powershell
git add docs/dst-manager/adr/ADR-DM-001-controlled-sheetset-editing.md docs/dst-manager/README.md src/dst_manager/config.py .env.example tests/unit/test_config.py
git commit -m "记录受控图纸集编辑决策并增加后缀配置"
```

### 任务 2：建立纯领域编辑规则与统一派生器

**文件：**

- Create: `src/dst_manager/domain/editing.py`
- Modify: `src/dst_manager/domain/models.py`
- Modify: `src/dst_manager/domain/planning.py`
- Create: `tests/unit/test_v021_editing.py`
- Modify: `tests/unit/test_core.py`

**接口：**

- 产出 `normalize_property_name(name: str) -> str`、`parse_property_csv(data: bytes) -> list[CustomPropertyDefinition]`、`format_sheet_title(base_title: str, ordinal: int | None, enabled: bool, suffix_type: int) -> str` 和 `derive_group_titles(groups: list[tuple[str, str, int]], enabled: bool, suffix_type: int) -> list[list[str]]`。
- 产出 `SuffixOptions(enabled: bool, suffix_type: Literal[1, 2])` 与 `derive_document_structure(document: SheetSetDocument, commands: list[dict[str, Any]], suffix_options: SuffixOptions) -> DerivedDocument`；其结果包含最终 `subsets`、受影响子集 ID、属性定义差异及图号/标题派生值。
- `build_structural_plan()` 改为消费 `DerivedDocument`，不得重复实现编号、标题或位置算法。

- [ ] **步骤 1：写领域规则的失败测试**

```python
def test_same_title_subsets_receive_continuous_chinese_suffixes():
    titles = derive_group_titles(
        [("4-10", "燃气管道平面图", 7), ("11-20", "燃气管道平面图", 10)],
        enabled=True,
        suffix_type=1,
    )
    assert titles[0][0] == "燃气管道平面图 (一)"
    assert titles[1][0] == "燃气管道平面图 (八)"


def test_normalize_property_name_rejects_autocad_case_collision():
    assert normalize_property_name(" Go ") == "Go"
    with pytest.raises(EditingError, match="CUSTOM_PROPERTY_NAME_DUPLICATE"):
        validate_property_definitions([("sheet", "go", ""), ("sheet", "Go", "")])
```

还必须覆盖：数字后缀、关闭后缀、全组单图纸无后缀、同名组按图号范围起始值排序、空标题/非法类型、UTF-8 BOM、非 UTF-8、额外 CSV 列、逗号外分隔符、空 `name`、同名同类型跳过、同名不同类型阻断、首次子集序号 `1`、批量插入和空子集拒绝。

- [ ] **步骤 2：运行领域测试确认失败**

运行：`uv run pytest tests/unit/test_v021_editing.py tests/unit/test_core.py -q`  
预期：失败，提示导入函数或派生规则不存在。

- [ ] **步骤 3：最小实现不可变领域规则**

新增以下数据结构，所有名称比较用 `casefold()`，显示名保留去首尾空白后的首次输入拼写：

```python
@dataclass(frozen=True, slots=True)
class CustomPropertyDefinition:
    type: Literal["sheetset", "sheet"]
    name: str
    default_value: str


@dataclass(frozen=True, slots=True)
class SuffixOptions:
    enabled: bool
    suffix_type: Literal[1, 2]


@dataclass(slots=True)
class DerivedSubset:
    acsm_id: str
    title: str
    number_range: str
    display_name: str
    sheets: list[Sheet]
```

将插入请求中的“序号”解释为位置，不接收图号和图纸标题。使用当前文档的全局图纸序列确定连续图号，并保留既有图号的起始值和零填充宽度；无既有图纸时从 `1`、宽度 `1` 开始。子集标题组以派生图号范围的数值起点排序；后缀由已校验的 `Settings` 计算，固定使用一个半角空格。

- [ ] **步骤 4：运行领域回归测试**

运行：`uv run pytest tests/unit/test_v021_editing.py tests/unit/test_core.py -q`  
预期：通过；现有命名测试改为断言新派生规则，而不再断言旧的标题猜测逻辑。

- [ ] **步骤 5：提交该独立变更**

```powershell
git add src/dst_manager/domain/editing.py src/dst_manager/domain/models.py src/dst_manager/domain/planning.py tests/unit/test_v021_editing.py tests/unit/test_core.py
git commit -m "实现图纸集受控编辑领域派生规则"
```

### 任务 3：实现 AcSm 属性定义与受控结构 DOM 写入

**文件：**

- Modify: `src/dst_manager/infrastructure/acsm_xml/document.py`
- Modify: `tests/unit/test_acsm_custom_properties.py`
- Modify: `tests/unit/test_core.py`

**接口：**

- 产出 `AcsmDocument.apply_property_definition_commands(commands: list[dict]) -> None`。
- 扩展 `AcsmDocument.apply_structural_commands(commands, base_revision)`，支持 `insert_subset`、批量 `insert_sheet`、`update_subset_title`，并拒绝 `move_sheet`、`reorder_sheet` 和含 `title` 的 `update_sheet`。
- 产出 `AcsmDocument.apply_derived_document(derived: DerivedDocument) -> None`，以同一结果写入子集名、图纸 Number/Title、属性定义和布局绑定前的受控字段。

- [ ] **步骤 1：为 DOM 变更写失败测试**

```python
def test_add_sheet_definition_sets_default_on_every_sheet(tiny_workspace):
    document = opened_document(tiny_workspace)
    document.apply_property_definition_commands([
        {"type": "add_custom_property", "property_type": "sheet", "name": "专业", "default_value": "燃气"}
    ])
    assert [sheet.custom_properties["专业"] for sheet in document.project(dst_parent).sheets] == ["燃气"]


def test_insert_subset_creates_nonempty_controlled_nodes(tiny_workspace):
    document = opened_document(tiny_workspace)
    document.apply_structural_commands([INSERT_SUBSET_COMMAND], "revision")
    assert len(document.project(dst_parent).subsets[-1].sheets) == 1
```

还必须覆盖删除 `sheet` 属性时从所有图纸移除、删除 `sheetset` 属性时只影响图纸集、大小写重复阻断、未知节点/属性/顺序保留、空属性值遵循已验证的缺失 `Value` 语义、首次子集模板节点、批量图纸节点与新 GUID 唯一性。

- [ ] **步骤 2：运行 DOM 测试确认失败**

运行：`uv run pytest tests/unit/test_acsm_custom_properties.py tests/unit/test_core.py -q`  
预期：失败，提示新增 DOM 命令或节点工厂不存在。

- [ ] **步骤 3：最小实现受控 DOM 工厂和写入**

从已验证的最小 AcSm 节点工厂创建 `AcSmCustomPropertyValue`、`AcSmSubset` 和 `AcSmSheet`；只修改受控 `AcSmProp` 与直属受控子树。新增属性的 `Flags` 固定为 `1`（`sheetset`）或 `2`（`sheet`），并保留 `vt`、未知兄弟节点和节点顺序。创建子集必须在同一命令内创建至少一张图纸；创建失败时抛出 `EMPTY_SUBSET`，不得写出半个节点。

```python
def apply_derived_document(self, derived: DerivedDocument) -> None:
    """将已经验证的最终结构写入受控 AcSm 节点，不重新计算业务规则。"""
```

- [ ] **步骤 4：运行 DOM 与 XML 往返测试**

运行：`uv run pytest tests/unit/test_acsm_custom_properties.py tests/unit/test_core.py -q`  
预期：通过；DST 解码/编码后受控字段等价，未知 XML 断言仍通过。

- [ ] **步骤 5：提交该独立变更**

```powershell
git add src/dst_manager/infrastructure/acsm_xml/document.py tests/unit/test_acsm_custom_properties.py tests/unit/test_core.py
git commit -m "支持受控属性定义与子集 DOM 变更"
```

### 任务 4：重构执行计划与 CAD 发布以支持新建独立 DWG

**文件：**

- Modify: `src/dst_manager/domain/planning.py`
- Modify: `src/dst_manager/application/cad_job.py`
- Modify: `src/dst_manager/application/service.py`
- Modify: `tests/unit/test_core.py`
- Modify: `tests/unit/test_publisher.py`
- Modify: `tests/system_autocad/test_capabilities.py`

**接口：**

- `build_structural_plan(workspace, commands, suffix_options) -> dict[str, Any]` 返回每个组的 `operation: "rebuild" | "create"`、`target_file`、`layouts`、`source_snapshot` 和 `source_target_file | None`。
- `CadJobRunner.run()` 必须处理 `create` 组：以模板快照作为暂存基础，发布新 DWG，不安排不存在的源 DWG 删除。
- `apply_derived_document()` 在 Handle 回读后执行，随后才执行 `validate()` 与编码回写。

- [ ] **步骤 1：写计划和发布的失败测试**

```python
def test_insert_subset_plan_creates_one_new_dwg_without_deleting_existing(tmp_path, workspace):
    plan = build_structural_plan(workspace, [INSERT_SUBSET_COMMAND], SuffixOptions(True, 1))
    group = plan["groups"][0]
    assert group["operation"] == "create"
    assert Path(group["target_file"]).name.endswith(".dwg")
    assert plan["deleted_subsets"] == []


def test_created_dwg_publish_failure_restores_dst_and_existing_dwgs(tmp_path, monkeypatch):
    root = tmp_path / "project"; root.mkdir()
    dst, existing, new_target = root / "set.dst", root / "old.dwg", root / "new.dwg"
    dst.write_bytes(b"old-dst"); existing.write_bytes(b"old-dwg")
    staging = tmp_path / "staging"; staging.mkdir()
    staged = {"dst": staging / "set.dst", "existing": staging / "old.dwg", "new": staging / "new.dwg"}
    staged["dst"].write_bytes(b"new-dst"); staged["existing"].write_bytes(b"new-old-dwg"); staged["new"].write_bytes(b"new-dwg")
    original_hashes = {path: file_sha256(path) for path in (dst, existing)}
    original_replace, calls = os.replace, itertools.count()
    def fail_on_second_replace(source, target):
        if next(calls) == 1:
            raise OSError("injected publish failure")
        return original_replace(source, target)
    monkeypatch.setattr("dst_manager.infrastructure.filesystem.publisher.os.replace", fail_on_second_replace)
    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher().publish("operation", root, {dst: staged["dst"], existing: staged["existing"], new_target: staged["new"]})
    assert {path: file_sha256(path) for path in (dst, existing)} == original_hashes
    assert not new_target.exists()
```

还必须覆盖批量插图重建、布局名碰撞、模板缺失、模板布局缺失、创建首个子集、创建后图号范围/后缀变化、创建/替换/删除混合任务在第 N 项发布失败时的回滚。

- [ ] **步骤 2：运行计划和发布测试确认失败**

运行：`uv run pytest tests/unit/test_core.py tests/unit/test_publisher.py -q`  
预期：失败，提示 `operation` 缺失或创建组被当作已有 DWG 重建。

- [ ] **步骤 3：最小实现计划与 CAD 任务分支**

`build_structural_plan()` 只消费任务 2 的最终结构；在 `create` 分支将选定模板复制到暂存区并由固定 `ScriptRenderer.render_rebuild()` 重新创建所有业务布局。发布清单必须同时包含 DST、重建目标、创建目标和删除目标；只锁定存在的文件，但为创建目标记录 `None` 基准哈希。Handle 结果必须与最终计划布局一一对应，才允许 `apply_derived_document()` 和发布。

- [ ] **步骤 4：运行非 CAD 回归与可选真实 CAD 验证**

运行：

```powershell
uv run pytest tests/unit/test_core.py tests/unit/test_publisher.py -q
$env:DST_MANAGER_RUN_AUTOCAD = "1"
uv run pytest tests/system_autocad -q
```

预期：非 CAD 测试通过；若本机具备 2016/2020、插件和私有样本，则两个版本都通过新建独立 DWG、批量布局复制和故障回滚验证；否则记录跳过原因。

- [ ] **步骤 5：提交该独立变更**

```powershell
git add src/dst_manager/domain/planning.py src/dst_manager/application/cad_job.py src/dst_manager/application/service.py tests/unit/test_core.py tests/unit/test_publisher.py tests/system_autocad/test_capabilities.py
git commit -m "支持子集独立DWG创建与安全发布"
```

### 任务 5：实现 CSV、应用服务、API 与序列化契约

**文件：**

- Modify: `src/dst_manager/application/service.py`
- Modify: `src/dst_manager/interfaces/api.py`
- Modify: `src/dst_manager/interfaces/serialization.py`
- Modify: `tests/integration/test_api.py`
- Modify: `tests/unit/test_v021_editing.py`

**接口：**

- 新增 `GET /api/custom-properties/template`，返回 `text/csv; charset=utf-8` 与精确内容 `type,name,default_value\r\n`。
- 新增 `POST /api/workspaces/{workspace_id}/custom-properties/import/preview`，请求体为 `base_revision_id` 与 CSV 文本；返回行级诊断、合并差异和可执行状态。
- 新增 `POST /api/workspaces/{workspace_id}/custom-properties/import`，使用相同 `base_revision_id` 和 CSV 文本执行经预览的命令。
- 新增 `GET /api/workspaces/{workspace_id}/custom-properties/export`，输出当前定义；`workspace_json()` 增加 `property_definitions`、子集 `title`、`number_range` 与只读 `display_name`。

- [ ] **步骤 1：写 API 失败测试**

```python
def test_property_csv_template_and_idempotent_import_preview(client, opened):
    template = client.get("/api/custom-properties/template")
    assert template.headers["content-type"].startswith("text/csv")
    assert template.content == b"type,name,default_value\r\n"
    preview = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import/preview",
        json={"base_revision_id": opened["revision_id"], "csv": "type,name,default_value\nsheet,专业,燃气\n"},
    )
    assert preview.json()["executable"] is True
    assert preview.json()["changes"][0]["action"] == "add"
```

覆盖 CSV 导出、UTF-8/表头/列数/类型/空名称/大小写冲突、同名不同类型、重复导入跳过、基准修订 409、插入图纸/子集命令的序号边界、旧命令返回 `COMMAND_UNSUPPORTED`，以及只读打开前后文件时间戳不变。

- [ ] **步骤 2：运行 API 测试确认失败**

运行：`uv run pytest tests/integration/test_api.py tests/unit/test_v021_editing.py -q`  
预期：失败，提示 CSV 端点和扩展序列化字段不存在。

- [ ] **步骤 3：最小实现服务与 API**

服务层必须把 CSV 转换为任务 2 的 `add_custom_property` 命令，不可直接写 DOM 或文件。`preview_changes()` 的白名单仅保留 `update_sheet_set`、`update_subset_title`、`update_sheet_properties`、`delete_sheet`、`insert_sheet`、`insert_subset` 和属性定义命令；显式拒绝 `move_sheet`、`reorder_sheet`、`renumber_sheets` 及带 `number`/`title` 的旧 `update_sheet`。属性变更仍使用现有预览、基准校验、修订与发布通路；涉及布局/DWG 的命令才请求 CAD Worker。

- [ ] **步骤 4：运行 API、只读与发布回归**

运行：`uv run pytest tests/integration/test_api.py tests/unit/test_v021_editing.py tests/unit/test_core.py -q`  
预期：通过；所有写操作都有 `base_revision_id` 校验，导入不会绕过发布器。

- [ ] **步骤 5：提交该独立变更**

```powershell
git add src/dst_manager/application/service.py src/dst_manager/interfaces/api.py src/dst_manager/interfaces/serialization.py tests/integration/test_api.py tests/unit/test_v021_editing.py
git commit -m "提供图纸集属性CSV与受控编辑API"
```

### 任务 6：替换 Web 编辑体验并覆盖端到端交互

**文件：**

- Modify: `web/src/App.vue`
- Modify: `web/src/style.css`
- Modify: `web/tests/e2e/main.spec.ts`

**接口：**

- UI 只提交任务 5 定义的命令和 CSV 端点；不本地计算图号、范围、图纸标题或后缀。
- `insertSheetForm` 字段为 `subsetId`、`sequence`、`direction`、`count`、`source`；`insertSubsetForm` 字段为 `sequence`、`direction`、`title`、`initialSheetCount`、`templateFile`、`templateLayout`。

- [ ] **步骤 1：写 Playwright 失败用例**

```ts
test("维护属性并按位置创建子集后预览派生变化", async ({ page }) => {
  // mock workspace 与 CSV/API 响应；添加 sheet 属性，创建初始两张图的子集。
  await page.getByRole("button", { name: "新建子集" }).click();
  await page.getByLabel("子集序号").fill("1");
  await page.getByLabel("初始图纸数").fill("2");
  await page.getByRole("button", { name: "预览变更" }).click();
  await expect(page.getByText("图号范围变化")).toBeVisible();
});
```

同时断言页面不存在“子集↑/子集↓”“移动到”“图纸标题输入框”“图纸图号输入框”；CSV 模板下载、导入错误行和导出入口可见；模板/布局、序号和数量错误在提交前提示。

- [ ] **步骤 2：运行 Playwright 用例确认失败**

运行：`Set-Location web; npm run test:e2e -- --grep "维护属性并按位置创建子集"`  
预期：失败，提示新表单或预览摘要不存在。

- [ ] **步骤 3：最小实现表单和预览展示**

删除 `queueMove`、`queueReorder`、可编辑 `sheet.number`/`sheet.title` 及子集上下移按钮。保留子集标题输入框但仅绑定 `update_subset_title`。增加属性定义管理面板、CSV 下载/上传/行级诊断和导出按钮；新增图纸与新增子集表单只接受规范字段。预览使用 API 的 `changes`、`execution_intent` 和派生摘要展示差异，不得在 Vue 内自行补算标题或范围。

- [ ] **步骤 4：运行 Web 类型检查、构建和端到端测试**

运行：

```powershell
Set-Location web
npm run build
npm run test:e2e
```

预期：构建与全部 Playwright 测试通过，现有修订历史和任务详情交互仍可用。

- [ ] **步骤 5：提交该独立变更**

```powershell
git add web/src/App.vue web/src/style.css web/tests/e2e/main.spec.ts
git commit -m "更新受控图纸集编辑界面"
```

### 任务 7：完成文档、全量验证与可追溯交付

**文件：**

- Modify: `docs/dst-manager/specs/SPEC-DM-001-v021-sheetset-editing-adjustment.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `.planning/plans/dst-manager/PLAN-DM-006-v021-controlled-sheetset-editing.md`
- Modify: `.planning/plans/dst-manager/README.md`
- Modify: `changelog.md`

**接口：**

- 不新增产品接口；记录实际验证命令、结果、跳过的真实 CAD 检查及 ADR/SPEC/PLAN 关联。

- [ ] **步骤 1：写交付核对清单并确认失败项**

在本计划的“实际验证记录”小节添加下列待核对项：领域后缀/CSV、DOM 往返、API 基准修订、发布回滚、Web 构建/Playwright、2016/2020 CAD。先运行一次全量非 CAD 命令，记录任何失败，而非提前修改计划状态。

- [ ] **步骤 2：运行全量非 CAD 验证**

运行：

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv run ruff check .
uv run pytest -q
uv lock --check
Set-Location web
npm ci
npm run build
npm run test:e2e
```

预期：Ruff、pytest、锁文件、构建和 Playwright 全部通过；公共克隆中因缺少私有样本跳过的测试须由测试输出明确标注。

- [ ] **步骤 3：运行可用环境下的真实 CAD 验证**

运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
$env:DST_MANAGER_RUN_AUTOCAD = "1"
uv run pytest tests/system_autocad -q
```

预期：若 2016/2020 Core Console、匹配插件和私有样本齐备，则两个版本通过；否则不伪造结果，在计划中记录环境缺失和恢复条件。

- [ ] **步骤 4：补全文档与状态**

将 `SPEC-DM-001` 状态改为 `accepted`（仅在实现与验收均完成后），在 ADR 中补充实施提交/验证证据；将本计划状态改为 `completed` 并添加实际验证记录。若任一阻断项未完成，保持 `active` 或改为 `blocked` 并写明原因和恢复条件。更新 README 索引及 `changelog.md`，只记录可核验的产品变化。

- [ ] **步骤 5：提交交付记录**

```powershell
git add docs/dst-manager .planning/plans/dst-manager changelog.md
git commit -m "完成v0.21受控图纸集编辑交付记录"
```

## 风险与缓解

- **首个子集的 AcSm 节点形状未经现有样本覆盖：** 在任务 3 用最小 XML 夹具断言 DOM 形状，并在任务 4 的 2016/2020 临时副本测试中验证 AutoCAD 可打开和保存。
- **标题派生与既有命名策略冲突：** 任务 2 以单一派生器替换 `_title_group()` 的猜测逻辑，任务 4 不允许 CAD、API 或 Web 再次派生。
- **创建 DWG 的发布回滚遗漏新增文件：** 任务 4 对创建、替换、删除及中途失败分别注入故障，断言新增目标被移除且旧文件哈希不变。
- **CSV 绕过属性范围和大小写规则：** CSV 只转换为领域命令，所有名称经 `normalize_property_name()` 和 `casefold()` 唯一性检查。
- **历史调用方继续调用旧命令：** 任务 5 在服务层白名单拒绝旧命令，任务 6 移除 UI 控件，API 集成测试断言返回稳定错误码。

## 完成标准

- `SPEC-DM-001` 的属性、CSV、插入、标题后缀、预览、错误、安全和兼容要求均对应至少一项自动化测试。
- 同名子集的图纸后缀按图号范围起始值分组并连续编号，单图纸分组不追加后缀；配置默认值和非法值符合规范。
- `sheet` 属性新增/删除会同步所有图纸，`sheetset` 属性仅作用于图纸集；AutoCAD 不区分大小写冲突被阻断。
- CSV 模板、导入预览、幂等合并、导出和行级诊断可用，且不能绕过基准修订与发布器。
- 新建子集始终至少含一张图纸并产生独立 DWG；批量插入与标题/范围/DWG/布局派生在同一计划中完成。
- API 和 Web 不再提供移动图纸、排序或手工图纸标题编辑；只读打开不写入。
- 发生 CAD 或发布故障时，正式目录不残留半发布状态；可用环境中 AutoCAD 2016/2020 均通过真实验证。
- `uv run ruff check .`、`uv run pytest -q`、`uv lock --check`、`npm run build` 和 `npm run test:e2e` 通过，或计划中有可复现的阻断记录。

## 实际验证记录

实施尚未开始。任务 7 完成后在此记录实际命令、通过数、跳过项和环境限制；在此之前本计划保持 `proposed`。
