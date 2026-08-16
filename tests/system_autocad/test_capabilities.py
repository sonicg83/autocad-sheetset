import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.infrastructure.acsm_xml import AcsmDocument
from dst_manager.infrastructure.acsm_xml.document import AcsmValidationError
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    CoreConsoleExecutor,
    ScriptRenderer,
    parse_handles,
)
from dst_manager.infrastructure.dst_codec import DstCodec

_SAMPLE_PROJECT = Path(__file__).parents[2] / "sample" / "project1"
pytestmark = [
    pytest.mark.skipif(os.environ.get("DST_MANAGER_RUN_AUTOCAD") != "1", reason="需要显式启用真实AutoCAD测试"),
    pytest.mark.skipif(not _SAMPLE_PROJECT.is_dir(), reason="公开仓库不分发真实工程样本"),
]


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_plugin_loads_and_reads_layout_handles(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    capability = CadCapability(
        version,
        Path(f"C:/Program Files/Autodesk/AutoCAD {version}/accoreconsole.exe"),
        root / "plugins" / f"autocad{version}" / "DstManager.AutoCAD.dll",
    )
    assert capability.available
    source = root / "sample" / "project1" / "GP-0000 封面.dwg"
    drawing = tmp_path / source.name
    shutil.copy2(source, drawing)
    script = tmp_path / "handles.scr"
    script.write_text(ScriptRenderer().render_handles(capability.plugin), encoding="mbcs")
    completed = CoreConsoleExecutor().run(capability, drawing, script, 120)
    handle_file = drawing.with_suffix(".dst-handles.txt")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert parse_handles(handle_file.read_text(encoding="utf-8"))


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_structural_title_change_rebuilds_dwg_and_dst(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    source_project = root / "sample" / "project1"
    shutil.copy2(source_project / "图纸集数据文件.dst", tmp_path / "图纸集数据文件.dst")
    shutil.copy2(source_project / "GP-0000 封面.dwg", tmp_path / "GP-0000 封面.dwg")
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=120,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(tmp_path / "图纸集数据文件.dst")
    sheet = workspace.document.subsets[0].sheets[0]
    job = service.execute_changes(workspace.id, workspace.revision_id, [{"type": "update_sheet", "sheet_id": sheet.acsm_id, "title": "封面测试"}], version)
    assert job["status"] == "QUEUED"
    result = service.run_next_job()
    assert result and result["status"] == "SUCCEEDED", result
    assert len(result["files"]) == 1
    assert result["files"][0]["duration_ms"] > 0
    assert result["files"][0]["peak_memory_bytes"] > 0
    assert result["files"][0]["staging_bytes"] > 0
    reopened = service.open_workspace(tmp_path / "图纸集数据文件.dst")
    changed = reopened.document.subsets[0].sheets[0]
    assert changed.title == "封面测试"
    assert changed.layout.layout_name == "0000 封面测试"
    assert changed.layout.handle
    assert (tmp_path / ".dst-manager" / "revisions" / result["id"] / "before" / "图纸集数据文件.dst").is_file()


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_missing_custom_value_insert_and_update_complete_before_publish(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    dst_name = "图纸集数据文件.dst"
    drawing_name = "GP-0000 封面.dwg"
    shutil.copy2(source_project / dst_name, tmp_path / dst_name)
    shutil.copy2(source_project / drawing_name, tmp_path / drawing_name)
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=180,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(tmp_path / dst_name)
    subset = workspace.document.subsets[0]
    existing = subset.sheets[0]
    assert existing.custom_properties["备注"] == ""
    commands = [
        {"type": "update_sheet_set", "custom_properties": {"版本": "B"}},
        {
            "type": "update_sheet",
            "sheet_id": existing.acsm_id,
            "title": "封面热修复验证",
            "custom_properties": {"备注": "", "出图比例": "1:500", "设计人": existing.custom_properties["设计人"]},
        },
        {
            "type": "insert_sheet",
            "target_subset_id": subset.acsm_id,
            "position": 1,
            "number": "0001",
            "title": "新增热修复验证",
            "custom_properties": {"备注": "", "出图比例": "1:500"},
            "source": {"type": "template_layout", "file": str(existing.layout.resolved_path), "layout": existing.layout.layout_name},
        },
    ]
    preview = service.preview_changes(workspace.id, workspace.revision_id, commands)
    assert preview["executable"] is True, preview
    job = service.execute_changes(workspace.id, workspace.revision_id, commands, version)
    assert job["status"] == "QUEUED", job

    result = service.run_next_job()

    assert result and result["status"] == "SUCCEEDED", result
    reopened = service.open_workspace(tmp_path / dst_name)
    final_subset = reopened.document.subsets[0]
    assert reopened.document.custom_properties["版本"] == "B"
    assert [sheet.title for sheet in final_subset.sheets] == ["封面热修复验证", "新增热修复验证"]
    assert all(sheet.custom_properties["备注"] == "" for sheet in final_subset.sheets)
    assert all(sheet.custom_properties["出图比例"] == "1:500" for sheet in final_subset.sheets)
    xml = AcsmDocument(DstCodec().decode_file(tmp_path / dst_name))
    sheetset_remark_values = xml.root.xpath(
        "//*[local-name()='AcSmSheetSet']/*[local-name()='AcSmCustomPropertyBag']"
        "/*[local-name()='AcSmCustomPropertyValue' and @propname='备注']"
        "/*[local-name()='AcSmProp' and @propname='Value']"
    )
    assert sheetset_remark_values == []
    for sheet in final_subset.sheets:
        value_nodes = xml.root.xpath(
            "//*[@ID=$sheet_id and local-name()='AcSmSheet']"
            "/*[local-name()='AcSmCustomPropertyBag']"
            "/*[local-name()='AcSmCustomPropertyValue' and @propname='备注']"
            "/*[local-name()='AcSmProp' and @propname='Value']",
            sheet_id=sheet.acsm_id,
        )
        assert value_nodes == []


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_five_dwg_groups_run_with_bounded_parallelism(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    dst_name = "图纸集数据文件.dst"
    shutil.copy2(source_project / dst_name, tmp_path / dst_name)
    source_document = AcsmDocument(DstCodec().decode_file(source_project / dst_name)).project(source_project)
    sheets = [subset.sheets[0] for subset in source_document.subsets[:5]]
    for drawing in {sheet.layout.resolved_path for sheet in sheets}:
        shutil.copy2(drawing, tmp_path / drawing.name)
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=180,
        cad_max_parallel=2,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(tmp_path / dst_name)
    commands = [{"type": "update_sheet", "sheet_id": subset.sheets[0].acsm_id, "title": f"{subset.sheets[0].title}-并行"} for subset in workspace.document.subsets[:5]]
    job = service.execute_changes(workspace.id, workspace.revision_id, commands, version)
    assert job["status"] == "QUEUED"
    result = service.run_next_job()
    assert result and result["status"] == "SUCCEEDED", result
    assert len(result["files"]) == 5
    assert all(item["status"] == "SUCCEEDED" for item in result["files"])
    assert all(item["duration_ms"] > 0 and item["peak_memory_bytes"] > 0 for item in result["files"])
    reopened = service.open_workspace(tmp_path / dst_name)
    assert all(subset.sheets[0].title.endswith("-并行") for subset in reopened.document.subsets[:5])


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_insert_delete_reorder_and_cross_subset_move(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    shutil.copy2(source_project / "图纸集数据文件.dst", tmp_path / "图纸集数据文件.dst")
    for name in ("GP-0001-0005 图纸目录(一)-(五).dwg", "GP-0006-0007 主要设备及材料表(一)-(二).dwg"):
        shutil.copy2(source_project / name, tmp_path / name)
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=180,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(tmp_path / "图纸集数据文件.dst")
    source_subset, target_subset = workspace.document.subsets[2], workspace.document.subsets[3]
    reordered_id = source_subset.sheets[0].acsm_id
    deleted_id = source_subset.sheets[2].acsm_id
    moved_id = source_subset.sheets[3].acsm_id
    template = source_subset.sheets[1]
    commands = [
        {"type": "reorder_sheet", "sheet_id": reordered_id, "position": 4},
        {"type": "delete_sheet", "sheet_id": deleted_id},
        {"type": "insert_sheet", "target_subset_id": source_subset.acsm_id, "position": 1, "number": "0998", "title": "新增测试", "source": {"type": "template_layout", "file": str(template.layout.resolved_path), "layout": template.layout.layout_name}},
        {"type": "move_sheet", "sheet_id": moved_id, "target_subset_id": target_subset.acsm_id, "position": 1},
    ]
    job = service.execute_changes(workspace.id, workspace.revision_id, commands, version)
    assert job["status"] == "QUEUED", job
    result = service.run_next_job()
    assert result and result["status"] == "SUCCEEDED", result
    reopened = service.open_workspace(tmp_path / "图纸集数据文件.dst")
    final_source, final_target = reopened.document.subsets[2], reopened.document.subsets[3]
    assert deleted_id not in {sheet.acsm_id for sheet in reopened.document.sheets}
    assert moved_id in {sheet.acsm_id for sheet in final_target.sheets}
    assert any(sheet.number == "0998" and sheet.title == "新增测试" for sheet in final_source.sheets)
    assert len(final_source.sheets) == 4 and len(final_target.sheets) == 3
    assert len({sheet.layout.handle for sheet in final_source.sheets + final_target.sheets}) == 7


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_delete_last_sheet_removes_subset_and_dwg(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]; source_project = root / "sample/project1"
    shutil.copy2(source_project / "图纸集数据文件.dst", tmp_path / "图纸集数据文件.dst")
    drawing = tmp_path / "GP-0000 封面.dwg"; shutil.copy2(source_project / drawing.name, drawing)
    settings=Settings(data_dir=tmp_path/"data",autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),autocad_2016_plugin=root/"plugins/autocad2016/DstManager.AutoCAD.dll",autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),autocad_2020_plugin=root/"plugins/autocad2020/DstManager.AutoCAD.dll",cad_timeout_seconds=120)
    service=DstManagerService(settings); workspace=service.open_workspace(tmp_path/"图纸集数据文件.dst"); subset=workspace.document.subsets[0]; sheet_id=subset.sheets[0].acsm_id
    job=service.execute_changes(workspace.id,workspace.revision_id,[{"type":"delete_sheet","sheet_id":sheet_id,"delete_empty_subset":True}],version); assert job["status"]=="QUEUED"
    result=service.run_next_job(); assert result and result["status"]=="SUCCEEDED",result
    reopened=service.open_workspace(tmp_path/"图纸集数据文件.dst"); assert subset.acsm_id not in {item.acsm_id for item in reopened.document.subsets}; assert not drawing.exists()
    assert (tmp_path/".dst-manager"/"revisions"/result["id"]/"before"/drawing.name).is_file()


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_largest_25_layout_group_rebuilds_in_order(version: str, tmp_path: Path):
    root=Path(__file__).parents[2]; source_project=root/"sample/project1"; shutil.copy2(source_project/"图纸集数据文件.dst",tmp_path/"图纸集数据文件.dst")
    drawing_name="GP-0038-0062 龙岗段入廊给水、再生水平面图(十六)-(四十).dwg"; shutil.copy2(source_project/drawing_name,tmp_path/drawing_name)
    settings=Settings(data_dir=tmp_path/"data",autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),autocad_2016_plugin=root/"plugins/autocad2016/DstManager.AutoCAD.dll",autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),autocad_2020_plugin=root/"plugins/autocad2020/DstManager.AutoCAD.dll",cad_timeout_seconds=900)
    service=DstManagerService(settings); workspace=service.open_workspace(tmp_path/"图纸集数据文件.dst"); subset=workspace.document.subsets[14]; assert len(subset.sheets)==25
    job=service.execute_changes(workspace.id,workspace.revision_id,[{"type":"renumber_sheets","subset_id":subset.acsm_id,"start":38,"width":4}],version); assert job["status"]=="QUEUED"
    result=service.run_next_job(); assert result and result["status"]=="SUCCEEDED",result
    rebuilt=service.open_workspace(tmp_path/"图纸集数据文件.dst").document.subsets[14].sheets; assert len(rebuilt)==25; assert [sheet.number for sheet in rebuilt]==[str(value).zfill(4) for value in range(38,63)]; assert len({sheet.layout.handle for sheet in rebuilt})==25


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_parallel_one_and_two_produce_equivalent_results(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    source_document = AcsmDocument(DstCodec().decode_file(source_project / "图纸集数据文件.dst")).project(source_project)
    source_sheets = [subset.sheets[0] for subset in source_document.subsets[:2]]
    outcomes = []
    for parallel in (1, 2):
        project = tmp_path / f"parallel-{parallel}"
        project.mkdir()
        shutil.copy2(source_project / "图纸集数据文件.dst", project / "图纸集数据文件.dst")
        for drawing in {sheet.layout.resolved_path for sheet in source_sheets}:
            shutil.copy2(drawing, project / drawing.name)
        settings = Settings(
            data_dir=project / "data",
            autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
            autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
            autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
            autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
            cad_timeout_seconds=180,
            cad_max_parallel=parallel,
        )
        service = DstManagerService(settings)
        workspace = service.open_workspace(project / "图纸集数据文件.dst")
        commands = [
            {"type": "update_sheet", "sheet_id": subset.sheets[0].acsm_id, "title": f"{subset.sheets[0].title}-等价"}
            for subset in workspace.document.subsets[:2]
        ]
        job = service.execute_changes(workspace.id, workspace.revision_id, commands, version)
        assert job["status"] == "QUEUED"
        result = service.run_next_job()
        assert result and result["status"] == "SUCCEEDED", result
        reopened = service.open_workspace(project / "图纸集数据文件.dst")
        outcomes.append(
            [
                (sheet.acsm_id, sheet.number, sheet.title, sheet.layout.layout_name)
                for subset in reopened.document.subsets[:2]
                for sheet in subset.sheets
            ]
        )
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_injected_second_dwg_failure_never_publishes_partial_files(version: str, tmp_path: Path, monkeypatch):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    dst_name = "图纸集数据文件.dst"
    shutil.copy2(source_project / dst_name, tmp_path / dst_name)
    source_document = AcsmDocument(DstCodec().decode_file(source_project / dst_name)).project(source_project)
    source_sheets = [subset.sheets[0] for subset in source_document.subsets[:2]]
    for drawing in {sheet.layout.resolved_path for sheet in source_sheets}:
        shutil.copy2(drawing, tmp_path / drawing.name)
    formal_files = [tmp_path / dst_name, *(tmp_path / sheet.layout.resolved_path.name for sheet in source_sheets)]
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in formal_files}
    original_run = CoreConsoleExecutor.run
    calls = 0

    def fail_third_console_call(self, capability, drawing, script, timeout):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise subprocess.CalledProcessError(1, [str(capability.console)], "", "INJECTED_DWG_FAILURE")
        return original_run(self, capability, drawing, script, timeout)

    monkeypatch.setattr(CoreConsoleExecutor, "run", fail_third_console_call)
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=180,
        cad_max_parallel=1,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(tmp_path / dst_name)
    commands = [
        {"type": "update_sheet", "sheet_id": subset.sheets[0].acsm_id, "title": f"{subset.sheets[0].title}-失败注入"}
        for subset in workspace.document.subsets[:2]
    ]
    job = service.execute_changes(workspace.id, workspace.revision_id, commands, version)
    assert job["status"] == "QUEUED"

    result = service.run_next_job()

    assert result and result["status"] == "FAILED"
    assert result["error_code"] == "CAD_PROCESS_FAILED"
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in formal_files}
    assert after == before
    assert {path.name for path in tmp_path.glob("*.dwg")} == {path.name for path in formal_files if path.suffix.lower() == ".dwg"}
    assert not (tmp_path / ".dst-manager" / "revisions" / result["id"] / "manifest.json").exists()


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_cad_success_then_dom_failure_keeps_formal_hashes(version: str, tmp_path: Path, monkeypatch):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    dst = tmp_path / "图纸集数据文件.dst"
    drawing = tmp_path / "GP-0000 封面.dwg"
    shutil.copy2(source_project / dst.name, dst)
    shutil.copy2(source_project / drawing.name, drawing)
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=180,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(dst)
    sheet = workspace.document.subsets[0].sheets[0]
    job = service.execute_changes(
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet", "sheet_id": sheet.acsm_id, "title": "DOM 失败注入"}],
        version,
    )
    assert job["status"] == "QUEUED"
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (dst, drawing)}

    def fail_dom(*_args, **_kwargs):
        raise AcsmValidationError("CUSTOM_PROPERTY_VALUE_DUPLICATED: 注入")

    monkeypatch.setattr(AcsmDocument, "apply_structural_commands", fail_dom)
    result = service.run_next_job()

    assert result and result["status"] == "FAILED"
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (dst, drawing)}
    assert after == before
    assert not (tmp_path / ".dst-manager" / "revisions" / result["id"] / "manifest.json").exists()
