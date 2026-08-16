import copy
import re
from pathlib import Path

from lxml import etree

from dst_manager.domain.models import (
    LayoutReference,
    Severity,
    Sheet,
    SheetSetDocument,
    Subset,
    ValidationIssue,
)

_ID_RE = re.compile(r"^g[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")
_HANDLE_RE = re.compile(r"^[0-9A-Fa-f]+$")


class AcsmValidationError(ValueError):
    @property
    def code(self) -> str:
        return str(self).split(":", 1)[0]


def _children(node: etree._Element, name: str):
    return [child for child in node if etree.QName(child).localname == name]


def _prop(node: etree._Element, name: str, default: str = "") -> str:
    for child in _children(node, "AcSmProp"):
        if child.get("propname") == name:
            return child.text or ""
    return default


def _set_prop(node: etree._Element, name: str, value: str) -> None:
    props = [child for child in _children(node, "AcSmProp") if child.get("propname") == name]
    if len(props) != 1:
        raise AcsmValidationError(f"CONTROLLED_PROPERTY_INVALID: {name}")
    props[0].text = value


def _custom_property_scope(node: etree._Element) -> str:
    flags = [child for child in _children(node, "AcSmProp") if child.get("propname") == "Flags"]
    if not flags:
        raise AcsmValidationError(f"CUSTOM_PROPERTY_FLAGS_MISSING: {node.get('propname', '')}")
    if len(flags) != 1:
        raise AcsmValidationError(f"CUSTOM_PROPERTY_FLAGS_INVALID: {node.get('propname', '')}")
    scope = (flags[0].text or "").strip()
    if scope not in {"1", "2"}:
        raise AcsmValidationError(f"CUSTOM_PROPERTY_FLAGS_INVALID: {node.get('propname', '')}")
    return scope


def _custom_property_values(node: etree._Element) -> list[etree._Element]:
    return [child for child in _children(node, "AcSmProp") if child.get("propname") == "Value"]


class AcsmDocument:
    """保留原DOM，仅投影受控字段。"""

    def __init__(self, xml: bytes):
        parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False, no_network=True)
        try:
            self.root = etree.fromstring(xml, parser)
        except etree.XMLSyntaxError as exc:
            raise AcsmValidationError(f"XML_INVALID: {exc}") from exc
        if etree.QName(self.root).localname != "AcSmDatabase":
            raise AcsmValidationError("XML_ROOT_INVALID: 根节点必须为AcSmDatabase")

    def clone(self) -> "AcsmDocument":
        result = object.__new__(AcsmDocument)
        result.root = copy.deepcopy(self.root)
        return result

    def to_bytes(self) -> bytes:
        return etree.tostring(self.root, xml_declaration=True, encoding="UTF-8")

    def semantic_bytes(self) -> bytes:
        """使用XML规范化比较DOM语义，不把声明和空元素写法视作差异。"""
        return etree.tostring(self.root, method="c14n", with_comments=True)

    def apply_metadata_commands(self, commands: list[dict]) -> None:
        """只更新已知属性；结构变化必须交给CAD重建任务。"""
        for command in commands:
            command_type = command.get("type")
            if command_type == "update_sheet":
                object_id = command.get("sheet_id")
                matches = self.root.xpath("//*[@ID=$object_id and local-name()='AcSmSheet']", object_id=object_id)
                if len(matches) != 1:
                    raise AcsmValidationError(f"SHEET_NOT_FOUND: {object_id}")
                sheet = matches[0]
                for field, prop_name in (("number", "Number"), ("title", "Title")):
                    if field in command:
                        _set_prop(sheet, prop_name, str(command[field]))
                self._set_custom_properties(sheet, command.get("custom_properties", {}), expected_scope="2")
            elif command_type == "update_sheet_set":
                matches = self.root.xpath("//*[local-name()='AcSmSheetSet']")
                if len(matches) != 1:
                    raise AcsmValidationError("SHEET_SET_INVALID")
                if "name" in command:
                    _set_prop(matches[0], "Name", str(command["name"]))
                self._set_custom_properties(matches[0], command.get("custom_properties", {}), expected_scope="1")
            elif command_type == "update_subset":
                subset_id = str(command.get("subset_id", ""))
                matches = self.root.xpath("//*[@ID=$subset_id and local-name()='AcSmSubset']", subset_id=subset_id)
                if len(matches) != 1:
                    raise AcsmValidationError(f"SUBSET_NOT_FOUND: {subset_id}")
                subset = matches[0]
                if "name" in command:
                    _set_prop(subset, "Name", str(command["name"]))
                if "position" in command:
                    parent = subset.getparent()
                    siblings = _children(parent, "AcSmSubset")
                    position = int(command["position"])
                    if position < 0 or position >= len(siblings):
                        raise AcsmValidationError(f"SUBSET_POSITION_INVALID: {position}")
                    parent.remove(subset)
                    remaining = _children(parent, "AcSmSubset")
                    if position >= len(remaining):
                        remaining[-1].addnext(subset) if remaining else parent.append(subset)
                    else:
                        remaining[position].addprevious(subset)
            else:
                raise AcsmValidationError(f"COMMAND_REQUIRES_CAD: {command_type}")

    def apply_structural_commands(self, commands: list[dict], base_revision: str) -> None:
        """在原始DOM上执行受控的插入、删除与移动，未知兄弟节点保持原位。"""
        from dst_manager.domain.planning import new_acsm_id

        def one(local_name: str, object_id: str) -> etree._Element:
            matches = self.root.xpath("//*[@ID=$object_id and local-name()=$local_name]", object_id=object_id, local_name=local_name)
            if len(matches) != 1:
                raise AcsmValidationError(f"{local_name.upper()}_NOT_FOUND: {object_id}")
            return matches[0]

        def insert_sheet(parent: etree._Element, node: etree._Element, position: int) -> None:
            sheets = _children(parent, "AcSmSheet")
            if position < 0 or position > len(sheets):
                raise AcsmValidationError(f"SHEET_POSITION_INVALID: {position}")
            if position == len(sheets):
                if sheets:
                    sheets[-1].addnext(node)
                else:
                    parent.append(node)
            else:
                sheets[position].addprevious(node)

        for command_index, command in enumerate(commands):
            kind = command.get("type")
            if kind == "update_sheet":
                node = one("AcSmSheet", str(command.get("sheet_id", "")))
                if "number" in command:
                    _set_prop(node, "Number", str(command["number"]))
                if "title" in command:
                    _set_prop(node, "Title", str(command["title"]))
                self._set_custom_properties(node, command.get("custom_properties", {}), expected_scope="2")
            elif kind in {"update_sheet_set", "update_subset"}:
                self.apply_metadata_commands([command])
            elif kind == "renumber_sheets":
                subset = one("AcSmSubset", str(command.get("subset_id", "")))
                start, width = int(command.get("start", 1)), int(command.get("width", 4))
                for offset, sheet in enumerate(_children(subset, "AcSmSheet")):
                    _set_prop(sheet, "Number", str(start + offset).zfill(width))
            elif kind == "delete_sheet":
                node = one("AcSmSheet", str(command.get("sheet_id", "")))
                parent = node.getparent()
                self._assert_no_external_id_reference(node)
                parent.remove(node)
                if not _children(parent, "AcSmSheet") and command.get("delete_empty_subset"):
                    self._assert_no_external_id_reference(parent)
                    parent.getparent().remove(parent)
            elif kind in {"move_sheet", "reorder_sheet"}:
                node = one("AcSmSheet", str(command.get("sheet_id", "")))
                source_parent = node.getparent()
                target_id = str(command.get("target_subset_id", source_parent.get("ID", "")))
                target = one("AcSmSubset", target_id)
                source_parent.remove(node)
                insert_sheet(target, node, int(command.get("position", len(_children(target, "AcSmSheet")))))
                if source_parent is not target and not _children(source_parent, "AcSmSheet") and command.get("delete_empty_source_subset"):
                    self._assert_no_external_id_reference(source_parent)
                    source_parent.getparent().remove(source_parent)
            elif kind == "insert_sheet":
                target = one("AcSmSubset", str(command.get("target_subset_id", "")))
                templates = _children(target, "AcSmSheet") or self.root.xpath("//*[local-name()='AcSmSheet']")
                if not templates:
                    raise AcsmValidationError("SHEET_TEMPLATE_NOT_FOUND")
                node = copy.deepcopy(templates[0])
                for index, item in enumerate(node.xpath(".//*[@ID] | self::*[@ID]")):
                    item.set("ID", new_acsm_id(base_revision, command_index, f"node-{index}"))
                node.set("ID", new_acsm_id(base_revision, command_index))
                _set_prop(node, "Number", str(command.get("number", "")))
                _set_prop(node, "Title", str(command.get("title", "")))
                self._set_custom_properties(node, command.get("custom_properties", {}), expected_scope="2", clear_others=True)
                insert_sheet(target, node, int(command.get("position", len(_children(target, "AcSmSheet")))))
            else:
                raise AcsmValidationError(f"COMMAND_UNSUPPORTED: {kind}")

    def apply_layout_bindings(self, bindings: dict[str, dict[str, str]], dst_dir: Path) -> None:
        for sheet_id, binding in bindings.items():
            matches = self.root.xpath("//*[@ID=$sheet_id and local-name()='AcSmSheet']", sheet_id=sheet_id)
            if len(matches) != 1:
                raise AcsmValidationError(f"SHEET_NOT_FOUND: {sheet_id}")
            layouts = _children(matches[0], "AcSmAcDbLayoutReference")
            if len(layouts) != 1:
                raise AcsmValidationError(f"SHEET_LAYOUT_COUNT: {sheet_id}")
            target = Path(binding["file"]).resolve()
            try:
                relative = target.relative_to(dst_dir.resolve())
            except ValueError as exc:
                raise AcsmValidationError(f"DWG_OUTSIDE_WORKSPACE: {target}") from exc
            _set_prop(layouts[0], "FileName", str(target))
            _set_prop(layouts[0], "Relative_FileName", ".\\" + str(relative).replace("/", "\\"))
            _set_prop(layouts[0], "Name", binding["layout"])
            _set_prop(layouts[0], "AcDbHandle", binding["handle"])

    def apply_subset_names(self, names: dict[str, str]) -> None:
        for subset_id, name in names.items():
            matches = self.root.xpath("//*[@ID=$subset_id and local-name()='AcSmSubset']", subset_id=subset_id)
            if len(matches) != 1:
                raise AcsmValidationError(f"SUBSET_NOT_FOUND: {subset_id}")
            _set_prop(matches[0], "Name", name)

    def _set_custom_properties(self, owner: etree._Element, values: dict, *, expected_scope: str, clear_others: bool = False) -> None:
        """按 AutoCAD 的 Value/Flags 语义更新已有自定义属性定义。"""
        custom_nodes = owner.xpath("./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue']")
        by_key: dict[tuple[str, str], etree._Element] = {}
        scopes_by_name: dict[str, set[str]] = {}
        value_nodes: dict[int, list[etree._Element]] = {}
        for node in custom_nodes:
            name = node.get("propname", "")
            scope = _custom_property_scope(node)
            key = (scope, name)
            if key in by_key:
                raise AcsmValidationError(f"CUSTOM_PROPERTY_DUPLICATED: {name}")
            by_key[key] = node
            scopes_by_name.setdefault(name, set()).add(scope)
            found_values = _custom_property_values(node)
            if len(found_values) > 1:
                raise AcsmValidationError(f"CUSTOM_PROPERTY_VALUE_DUPLICATED: {name}")
            value_nodes[id(node)] = found_values

        if clear_others:
            for (scope, _), node in by_key.items():
                if scope != expected_scope:
                    continue
                for value_node in value_nodes[id(node)]:
                    node.remove(value_node)
                value_nodes[id(node)] = []

        for raw_name, raw_value in values.items():
            name, value = str(raw_name), str(raw_value)
            node = by_key.get((expected_scope, name))
            if node is None:
                if name in scopes_by_name:
                    raise AcsmValidationError(f"CUSTOM_PROPERTY_SCOPE_MISMATCH: {name}")
                raise AcsmValidationError(f"CUSTOM_PROPERTY_NOT_FOUND: {name}")
            current_nodes = value_nodes[id(node)]
            current_value = current_nodes[0].text or "" if current_nodes else ""
            if current_value == value:
                continue
            if not value:
                if current_nodes:
                    node.remove(current_nodes[0])
                    value_nodes[id(node)] = []
                continue
            if current_nodes:
                current_nodes[0].text = value
                continue
            flags_node = next(child for child in _children(node, "AcSmProp") if child.get("propname") == "Flags")
            value_node = etree.Element(flags_node.tag, {"propname": "Value", "vt": "8"})
            value_node.text = value
            value_node.tail = flags_node.tail
            flags_node.addnext(value_node)
            value_nodes[id(node)] = [value_node]

    def _custom_property_issues(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for owner in self.root.xpath("//*[local-name()='AcSmCustomPropertyBag']/.."):
            seen: set[tuple[str, str]] = set()
            for node in owner.xpath("./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue']"):
                name = node.get("propname", "")
                try:
                    scope = _custom_property_scope(node)
                except AcsmValidationError as exc:
                    code = str(exc).split(":", 1)[0]
                    issues.append(ValidationIssue(code, Severity.ERROR, f"自定义属性“{name}”的 Flags 无效", owner.get("ID")))
                    continue
                key = (scope, name)
                if key in seen:
                    issues.append(ValidationIssue("CUSTOM_PROPERTY_DUPLICATED", Severity.ERROR, f"自定义属性“{name}”重复", owner.get("ID")))
                seen.add(key)
                if len(_custom_property_values(node)) > 1:
                    issues.append(ValidationIssue("CUSTOM_PROPERTY_VALUE_DUPLICATED", Severity.ERROR, f"自定义属性“{name}”存在多个 Value", owner.get("ID")))
        return issues

    def _assert_no_external_id_reference(self, owned: etree._Element) -> None:
        owned_ids = {node.get("ID") for node in owned.xpath(".//*[@ID] | self::*[@ID]") if node.get("ID")}
        if not owned_ids:
            return
        for node in self.root.iter():
            if node is owned or owned in node.iterancestors() or node in owned.iterdescendants():
                continue
            values = list(node.attrib.values()) + ([node.text] if node.text else [])
            if any(object_id in value for object_id in owned_ids for value in values):
                raise AcsmValidationError(f"UNKNOWN_REFERENCE_BLOCKED: {node.get('ID', etree.QName(node).localname)}")

    def validate(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = self._custom_property_issues()
        seen: set[str] = set()
        sheet_sets = self.root.xpath("//*[local-name()='AcSmSheetSet']")
        if not sheet_sets:
            issues.append(ValidationIssue("SHEET_SET_MISSING", Severity.ERROR, "缺少AcSmSheetSet节点"))
        if not _prop(self.root, "DbVersion"):
            issues.append(ValidationIssue("DATABASE_VERSION_MISSING", Severity.ERROR, "缺少AcSm数据库版本"))
        for node in self.root.iter():
            object_id = node.get("ID")
            if not object_id:
                continue
            if object_id in seen:
                issues.append(ValidationIssue("DUPLICATE_ACSM_ID", Severity.ERROR, "AcSm ID重复", object_id))
            seen.add(object_id)
            if not _ID_RE.fullmatch(object_id):
                issues.append(ValidationIssue("INVALID_ACSM_ID", Severity.ERROR, "AcSm ID格式无效", object_id))
        for node in self.root.xpath("//*[local-name()='AcSmSheet']"):
            layouts = _children(node, "AcSmAcDbLayoutReference")
            if len(layouts) != 1:
                issues.append(ValidationIssue("SHEET_LAYOUT_COUNT", Severity.ERROR, "图纸必须恰好有一个布局引用", node.get("ID")))
                continue
            layout = layouts[0]
            required = ("FileName", "Relative_FileName", "Name", "AcDbHandle")
            for name in required:
                if not _prop(layout, name):
                    issues.append(ValidationIssue("LAYOUT_FIELD_MISSING", Severity.ERROR, f"布局缺少{name}", node.get("ID")))
            handle = _prop(layout, "AcDbHandle")
            if handle and not _HANDLE_RE.fullmatch(handle):
                issues.append(ValidationIssue("LAYOUT_HANDLE_INVALID", Severity.ERROR, "布局Handle无效", node.get("ID")))
            if not _prop(node, "Number") or not _prop(node, "Title"):
                issues.append(ValidationIssue("SHEET_FIELD_MISSING", Severity.ERROR, "图纸缺少Number或Title", node.get("ID")))
        return issues

    def project(self, dst_dir: Path, root_override: Path | None = None) -> SheetSetDocument:
        sheet_set_nodes = self.root.xpath("//*[local-name()='AcSmSheetSet']")
        if not sheet_set_nodes:
            raise AcsmValidationError("SHEET_SET_MISSING")
        sheet_set = sheet_set_nodes[0]
        subsets: list[Subset] = []
        for order, subset_node in enumerate(self.root.xpath("//*[local-name()='AcSmSubset']")):
            subset = Subset(subset_node.get("ID", ""), _prop(subset_node, "Name"), order)
            # 只收集此子集直接拥有的图纸，避免嵌套子集重复投影。
            for sheet_node in _children(subset_node, "AcSmSheet"):
                layout_nodes = _children(sheet_node, "AcSmAcDbLayoutReference")
                if not layout_nodes:
                    continue
                layout_node = layout_nodes[0]
                layout = LayoutReference(
                    _prop(layout_node, "FileName"),
                    _prop(layout_node, "Relative_FileName"),
                    _prop(layout_node, "Name"),
                    _prop(layout_node, "AcDbHandle"),
                )
                custom: dict[str, str] = {}
                for value in sheet_node.xpath("./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue']"):
                    try:
                        if _custom_property_scope(value) == "2":
                            custom[value.get("propname", "")] = _prop(value, "Value")
                    except AcsmValidationError:
                        continue
                subset.sheets.append(Sheet(sheet_node.get("ID", ""), _prop(sheet_node, "Number"), _prop(sheet_node, "Title"), layout, custom))
            subsets.append(subset)
        sheet_set_custom: dict[str, str] = {}
        for value in sheet_set.xpath("./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue']"):
            try:
                if _custom_property_scope(value) == "1":
                    sheet_set_custom[value.get("propname", "")] = _prop(value, "Value")
            except AcsmValidationError:
                continue
        document = SheetSetDocument(self.root.get("ID", ""), _prop(sheet_set, "Name"), subsets, sheet_set_custom, self.validate())
        self.resolve_paths(document, dst_dir, root_override)
        return document

    @staticmethod
    def resolve_paths(document: SheetSetDocument, dst_dir: Path, root_override: Path | None = None) -> None:
        for sheet in document.sheets:
            reference = sheet.layout
            relative_text = reference.relative_file_name.replace("\\", "/").removeprefix("./")
            candidates = [
                (dst_dir / relative_text, "relative"),
                (Path(reference.file_name), "absolute"),
                (dst_dir / Path(reference.file_name.replace("\\", "/")).name, "basename"),
            ]
            if root_override is not None:
                candidates.append((root_override.resolve() / Path(reference.file_name.replace("\\", "/")).name, "root_override"))
            for candidate, source in candidates:
                if candidate.is_file():
                    reference.resolved_path = candidate.resolve()
                    reference.resolution_source = source
                    break
            if reference.resolved_path is None:
                document.diagnostics.append(ValidationIssue("DWG_PATH_NOT_FOUND", Severity.ERROR, "找不到布局引用的DWG", sheet.acsm_id, reference.file_name))
