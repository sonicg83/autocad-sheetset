import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from dst_manager.application.cad_job import CadJobRunner, RebuildWorkUnit
from dst_manager.domain.models import (
    LayoutReference,
    Sheet,
    SheetSetDocument,
    Workspace,
)
from dst_manager.domain.planning import derive_subset_and_dwg_name
from dst_manager.infrastructure.acsm_xml import AcsmDocument
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    decode_console_output,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.dst_codec.codec import _DECODE, _ENCODE
from dst_manager.infrastructure.logging_text import (
    sanitize_log_text,
    validate_log_bytes,
)
from dst_manager.interfaces.cli import _worker_summary
from dst_manager.interfaces.cli import app as cli_app


def test_mapping_all_bytes(): assert bytes(range(256)).translate(_ENCODE).translate(_DECODE)==bytes(range(256))


def test_log_text_is_strict_utf8_without_disallowed_controls(tmp_path):
    text = sanitize_log_text("中文\x00错误\x1b[31m\t正常\n")
    encoded = text.encode("utf-8")
    validate_log_bytes(encoded)
    assert b"\x00" not in encoded
    assert "\\x00" in text and "\\x1b" in text
    log_path = tmp_path / "中文工程" / "运行错误.log"
    log_path.parent.mkdir()
    log_path.write_text(text, encoding="utf-8")
    validate_log_bytes(log_path.read_bytes())


def test_windows_console_output_is_decoded_before_utf8_logging():
    text = "中文错误\x00"
    decoded_mbcs = decode_console_output(text.encode("mbcs"))
    decoded_utf16 = decode_console_output(text.encode("utf-16"))
    assert decoded_mbcs == decoded_utf16 == "中文错误\\x00"
    validate_log_bytes(decoded_mbcs.encode("utf-8"))


def test_failed_core_console_output_is_archived_in_per_dwg_log(tmp_path):
    source = tmp_path / "来源.dwg"
    source.write_bytes(b"source")
    staging = tmp_path / "staging"
    scripts = tmp_path / "scripts"
    logs = tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    unit = RebuildWorkUnit(
        index=0,
        group={
            "source_target_file": str(source),
            "target_file": str(tmp_path / "目标.dwg"),
            "layouts": [{"source_file": str(source), "source_layout": "布局1", "target_layout": "001 平面"}],
        },
        source_snapshot=source,
        staging_dir=staging,
        scripts_dir=scripts,
        logs_dir=logs,
        timeout=30,
    )
    database = Mock()
    runner = CadJobRunner(database, Mock(), Mock(), 30)
    runner.executor = Mock()
    runner.executor.run.side_effect = subprocess.CalledProcessError(7, ["accoreconsole.exe"], "布局输出", "CAD 错误输出")
    workspace = Workspace("workspace", tmp_path, tmp_path / "test.dst", "revision", SheetSetDocument("db", "图纸集", []))

    with pytest.raises(subprocess.CalledProcessError):
        runner._rebuild_group("job-1", workspace, CadCapability("2020", None, tmp_path / "plugin.dll"), unit)

    log = (logs / "group-000.log").read_text(encoding="utf-8")
    assert "Core Console：重建布局（退出码 7）stdout" in log
    assert "布局输出" in log and "CAD 错误输出" in log


def test_worker_stdout_summary_excludes_payload_and_paths():
    result = {
        "id": "job-1",
        "status": "FAILED",
        "attempt": 2,
        "error_code": "CAD_TIMEOUT",
        "payload": {"commands": [{"secret": "不要输出"}]},
        "files": [
            {"status": "SUCCEEDED", "target_path": r"C:\\客户\\A.dwg"},
            {"status": "FAILED", "target_path": r"C:\\客户\\B.dwg"},
        ],
    }

    summary = _worker_summary(result, 123)

    assert summary == {
        "job_id": "job-1",
        "status": "FAILED",
        "attempt": 2,
        "dwg_succeeded": 1,
        "dwg_failed": 1,
        "duration_ms": 123,
        "error_code": "CAD_TIMEOUT",
    }
    assert "payload" not in summary and "files" not in summary


@pytest.mark.parametrize(("status", "error_code"), [("SUCCEEDED", None), ("FAILED", "CAD_TIMEOUT")])
def test_worker_cli_writes_only_one_line_summary(monkeypatch, status, error_code):
    result = {
        "id": "job-1",
        "status": status,
        "attempt": 1,
        "error_code": error_code,
        "payload": {"commands": [{"secret": "不要输出"}]},
        "files": [{"status": status, "target_path": r"C:\\客户\\A.dwg"}],
    }

    class FakeService:
        def __init__(self):
            self.calls = 0

        def run_next_job(self):
            self.calls += 1
            return result if self.calls == 1 else None

    monkeypatch.setattr("dst_manager.interfaces.cli.DstManagerService", FakeService)
    completed = CliRunner().invoke(cli_app, ["worker", "--once"])

    assert completed.exit_code == 0
    lines = completed.stdout.strip().splitlines()
    assert len(lines) == 1
    summary = json.loads(lines[0])
    assert summary["job_id"] == "job-1" and summary["status"] == status
    assert "payload" not in completed.stdout and "commands" not in completed.stdout and "客户" not in completed.stdout
def test_golden_counts_and_relocation():
    dst=Path("sample/project1/图纸集数据文件.dst")
    if not dst.is_file(): pytest.skip("公开仓库不分发黄金工程样本")
    doc=AcsmDocument(DstCodec().decode_file(dst)).project(dst.parent)
    manifest=json.loads(Path("tests/golden/project1_manifest.json").read_text(encoding="utf-8")); files=[{"name":path.name,"size":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(dst.parent.iterdir()) if path.is_file() and path.suffix.lower() in {".dst",".dwg"}]; digest=hashlib.sha256(json.dumps(files,ensure_ascii=False,separators=(",",":"),sort_keys=True).encode()).hexdigest()
    assert len(files)==manifest["file_count"] and sum(item["size"] for item in files)==manifest["total_size"] and digest==manifest["files_digest"]
    assert (len(doc.sheets),len(doc.subsets))==(manifest["sheet_count"],manifest["subset_count"]); assert all(x.layout.resolved_path for x in doc.sheets)


def test_real_project_read_only_structure_profiles():
    """从真实黄金工程固定小型、约 300 图纸和大布局组的只读结构基线。"""
    dst = Path("sample/project1/图纸集数据文件.dst")
    if not dst.is_file():
        pytest.skip("公开仓库不分发黄金工程样本")
    before = {path: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()) for path in dst.parent.glob("*") if path.is_file()}
    doc = AcsmDocument(DstCodec().decode_file(dst)).project(dst.parent)
    profiles = {
        "small": len(doc.subsets[0].sheets),
        "around_300": len(doc.sheets),
        "large_layout_group": max(len(subset.sheets) for subset in doc.subsets),
    }
    assert profiles == {"small": 1, "around_300": 298, "large_layout_group": 25}
    after = {path: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()) for path in dst.parent.glob("*") if path.is_file()}
    assert after == before
    assert not (dst.parent / ".dst-manager").exists()
def test_unknown_preserved(tiny_workspace):
    dst,sheet_id=tiny_workspace; doc=AcsmDocument(DstCodec().decode_file(dst)); doc.apply_metadata_commands([{"type":"update_sheet","sheet_id":sheet_id,"title":"修改后","custom_properties":{"比例":"1:200"}}]); output=doc.to_bytes(); assert b'keep="yes"' in output and "修改后" in output.decode()

def test_sheet_set_and_sheet_custom_properties_roundtrip(tiny_workspace):
    dst,sheet_id=tiny_workspace
    doc=AcsmDocument(DstCodec().decode_file(dst))
    doc.apply_metadata_commands([
        {"type":"update_sheet_set","name":"新图纸集","custom_properties":{"项目号":"P-001"}},
        {"type":"update_sheet","sheet_id":sheet_id,"custom_properties":{"比例":"1:200"}},
    ])
    projected=AcsmDocument(doc.to_bytes()).project(dst.parent)
    assert projected.name=="新图纸集"
    assert projected.custom_properties=={"项目号":"P-001"}
    assert projected.sheets[0].custom_properties=={"比例":"1:200"}

def test_legacy_naming_policy_derives_subset_and_dwg():
    sheets=[Sheet("1","0001","图纸目录(一)",LayoutReference("","","","")),Sheet("2","0005","图纸目录(五)",LayoutReference("","","",""))]
    subset_name,dwg=derive_subset_and_dwg_name(Path("GP-0001-0005 图纸目录(一)-(五).dwg"),sheets)
    assert subset_name=="1-5 图纸目录" and dwg.name=="GP-0001-0005 图纸目录(一)-(五).dwg"
