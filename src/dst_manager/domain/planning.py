import copy
import re
import uuid
from pathlib import Path
from typing import Any

from dst_manager.domain.models import LayoutReference, Sheet, Workspace


class PlanningError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_UNSAFE_NAME = re.compile(r"[<>/\\\":;?*|=\r\n\x00-\x1f]")
_ORDINAL = re.compile(r"^(.*?)[(（]([一二三四五六七八九十百]+)[)）]$")


def derive_layout_name(number: str, title: str) -> str:
    name = f"{number.strip()} {title.strip()}".strip()
    if not name or len(name) > 255 or _UNSAFE_NAME.search(name):
        raise PlanningError("LAYOUT_NAME_INVALID", f"布局名无效：{name!r}")
    return name


def _display_number(number: str) -> str:
    return str(int(number)) if number.isdigit() else number


def _title_group(titles: list[str]) -> tuple[str, str]:
    matches = [_ORDINAL.fullmatch(title.strip()) for title in titles]
    if all(matches) and len({match.group(1) for match in matches if match}) == 1:
        base = matches[0].group(1)
        return base, f"{base}({matches[0].group(2)})-({matches[-1].group(2)})" if len(matches) > 1 else titles[0]
    if len(set(titles)) == 1:
        return titles[0], titles[0]
    return f"{titles[0]}-{titles[-1]}", f"{titles[0]}-{titles[-1]}"


def derive_subset_and_dwg_name(existing: Path, sheets: list[Sheet]) -> tuple[str, Path]:
    if not sheets:
        raise PlanningError("EMPTY_SUBSET", "空子集不能派生命名")
    base_title, file_title = _title_group([sheet.title for sheet in sheets])
    first, last = sheets[0].number, sheets[-1].number
    number_range = first if len(sheets) == 1 else f"{first}-{last}"
    display_range = _display_number(first) if len(sheets) == 1 else f"{_display_number(first)}-{_display_number(last)}"
    prefix_match = re.match(r"^(.*?-)(?=\d)", existing.stem)
    prefix = prefix_match.group(1) if prefix_match else ""
    subset_name = f"{display_range} {base_title}"
    file_name = f"{prefix}{number_range} {file_title}.dwg"
    if _UNSAFE_NAME.search(file_name) or len(file_name) > 240:
        raise PlanningError("DWG_FILE_NAME_INVALID", f"派生DWG文件名无效：{file_name}")
    return subset_name, existing.with_name(file_name)


def new_acsm_id(base_revision: str, command_index: int, suffix: str = "sheet") -> str:
    value = uuid.uuid5(uuid.NAMESPACE_URL, f"dst-manager:{base_revision}:{command_index}:{suffix}")
    return "g" + str(value).upper()


def build_structural_plan(workspace: Workspace, commands: list[dict[str, Any]]) -> dict[str, Any]:
    subsets = copy.deepcopy(workspace.document.subsets)
    subset_by_id = {subset.acsm_id: subset for subset in subsets}
    sources: dict[str, dict[str, str]] = {
        sheet.acsm_id: {"type": "existing_snapshot", "file": str(sheet.layout.resolved_path or ""), "layout": sheet.layout.layout_name}
        for sheet in workspace.document.sheets
    }
    affected: set[str] = set()
    empty_subset_confirmed: set[str] = set()

    def locate(sheet_id: str):
        for subset in subsets:
            for index, sheet in enumerate(subset.sheets):
                if sheet.acsm_id == sheet_id:
                    return subset, index, sheet
        raise PlanningError("SHEET_NOT_FOUND", f"找不到图纸：{sheet_id}")

    for command_index, command in enumerate(commands):
        kind = command.get("type")
        if kind == "update_sheet":
            subset, _, sheet = locate(str(command.get("sheet_id", "")))
            if "number" in command:
                sheet.number = str(command["number"])
                affected.add(subset.acsm_id)
            if "title" in command:
                sheet.title = str(command["title"])
                affected.add(subset.acsm_id)
            sheet.custom_properties.update({str(key): str(value) for key, value in command.get("custom_properties", {}).items()})
        elif kind in {"update_sheet_set", "update_subset"}:
            continue
        elif kind == "renumber_sheets":
            subset_id = str(command.get("subset_id", ""))
            if subset_id not in subset_by_id:
                raise PlanningError("SUBSET_NOT_FOUND", f"找不到子集：{subset_id}")
            start, width = int(command.get("start", 1)), int(command.get("width", 4))
            if start < 0 or width < 1 or width > 12:
                raise PlanningError("RENUMBER_ARGUMENT_INVALID", "重编号起点或宽度无效")
            for offset, sheet in enumerate(subset_by_id[subset_id].sheets):
                sheet.number = str(start + offset).zfill(width)
            affected.add(subset_id)
        elif kind == "delete_sheet":
            subset, index, sheet = locate(str(command.get("sheet_id", "")))
            subset.sheets.pop(index)
            affected.add(subset.acsm_id)
            if command.get("delete_empty_subset"):
                empty_subset_confirmed.add(subset.acsm_id)
        elif kind in {"move_sheet", "reorder_sheet"}:
            source_subset, source_index, sheet = locate(str(command.get("sheet_id", "")))
            source_subset.sheets.pop(source_index)
            target_id = str(command.get("target_subset_id", source_subset.acsm_id))
            if target_id not in subset_by_id:
                raise PlanningError("SUBSET_NOT_FOUND", f"找不到目标子集：{target_id}")
            target = subset_by_id[target_id]
            position = int(command.get("position", len(target.sheets)))
            if position < 0 or position > len(target.sheets):
                raise PlanningError("SHEET_POSITION_INVALID", f"图纸位置越界：{position}")
            target.sheets.insert(position, sheet)
            affected.update({source_subset.acsm_id, target.acsm_id})
            if command.get("delete_empty_source_subset"):
                empty_subset_confirmed.add(source_subset.acsm_id)
        elif kind == "insert_sheet":
            target_id = str(command.get("target_subset_id", ""))
            if target_id not in subset_by_id:
                raise PlanningError("SUBSET_NOT_FOUND", f"找不到目标子集：{target_id}")
            target = subset_by_id[target_id]
            source = command.get("source") or {}
            source_file = Path(str(source.get("file", ""))).expanduser().resolve()
            source_layout = str(source.get("layout", ""))
            if source.get("type") not in {"existing_snapshot", "template_layout"} or not source_file.is_file() or not source_layout:
                raise PlanningError("LAYOUT_SOURCE_INVALID", "新增图纸的来源文件或布局无效")
            sheet_id = new_acsm_id(workspace.revision_id, command_index)
            number, title = str(command.get("number", "")), str(command.get("title", ""))
            sheet = Sheet(sheet_id, number, title, LayoutReference("", "", derive_layout_name(number, title), ""), {str(key): str(value) for key, value in command.get("custom_properties", {}).items()})
            position = int(command.get("position", len(target.sheets)))
            if position < 0 or position > len(target.sheets):
                raise PlanningError("SHEET_POSITION_INVALID", f"图纸位置越界：{position}")
            target.sheets.insert(position, sheet)
            sources[sheet_id] = {"type": str(source["type"]), "file": str(source_file), "layout": source_layout}
            affected.add(target_id)
        else:
            raise PlanningError("COMMAND_UNSUPPORTED", f"不支持的命令：{kind}")

    groups = []
    deleted_subsets = []
    for subset in subsets:
        if subset.acsm_id not in affected:
            continue
        original_domain = next(item for item in workspace.document.subsets if item.acsm_id == subset.acsm_id)
        if not subset.sheets:
            if subset.acsm_id not in empty_subset_confirmed:
                raise PlanningError("EMPTY_SUBSET_CONFIRMATION_REQUIRED", "子集变空时必须明确确认删除子集及主DWG")
            target = next((sheet.layout.resolved_path for sheet in original_domain.sheets if sheet.layout.resolved_path), None)
            if target:
                deleted_subsets.append({"subset_id": subset.acsm_id, "target_file": str(target)})
            continue
        target_path = next((sheet.layout.resolved_path for sheet in original_domain.sheets if sheet.layout.resolved_path), None)
        if target_path is None:
            raise PlanningError("TARGET_DWG_NOT_FOUND", f"子集没有可用主DWG：{subset.acsm_id}")
        layouts = []
        names: set[str] = set()
        for sheet in subset.sheets:
            name = derive_layout_name(sheet.number, sheet.title)
            if name.casefold() in names:
                raise PlanningError("DUPLICATE_LAYOUT_NAME", f"目标DWG内布局名重复：{name}")
            names.add(name.casefold())
            source = sources[sheet.acsm_id]
            if not source["file"] or not Path(source["file"]).is_file():
                raise PlanningError("LAYOUT_SOURCE_NOT_FOUND", f"找不到源DWG：{source['file']}")
            layouts.append({"sheet_id": sheet.acsm_id, "number": sheet.number, "title": sheet.title, "custom_properties": sheet.custom_properties, "source_type": source["type"], "source_file": source["file"], "source_layout": source["layout"], "target_layout": name})
        subset_name, final_target = derive_subset_and_dwg_name(Path(target_path), subset.sheets)
        groups.append({"subset_id": subset.acsm_id, "subset_name": subset_name, "source_target_file": str(target_path), "target_file": str(final_target), "layouts": layouts})
    final_targets = [group["target_file"].casefold() for group in groups]
    if len(final_targets) != len(set(final_targets)):
        raise PlanningError("DWG_TARGET_COLLISION", "多个子集派生出相同的目标DWG文件名")
    return {"groups": groups, "deleted_subsets": deleted_subsets, "affected_subset_ids": sorted(affected)}
