import hashlib
import json
from pathlib import Path

import pytest

from dst_manager.domain.models import LayoutReference, Sheet
from dst_manager.domain.planning import derive_subset_and_dwg_name
from dst_manager.infrastructure.acsm_xml import AcsmDocument
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.dst_codec.codec import _DECODE, _ENCODE


def test_mapping_all_bytes(): assert bytes(range(256)).translate(_ENCODE).translate(_DECODE)==bytes(range(256))
def test_golden_counts_and_relocation():
    dst=Path("sample/project1/图纸集数据文件.dst")
    if not dst.is_file(): pytest.skip("公开仓库不分发黄金工程样本")
    doc=AcsmDocument(DstCodec().decode_file(dst)).project(dst.parent)
    manifest=json.loads(Path("tests/golden/project1_manifest.json").read_text(encoding="utf-8")); files=[{"name":path.name,"size":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(dst.parent.iterdir()) if path.is_file() and path.suffix.lower() in {".dst",".dwg"}]; digest=hashlib.sha256(json.dumps(files,ensure_ascii=False,separators=(",",":"),sort_keys=True).encode()).hexdigest()
    assert len(files)==manifest["file_count"] and sum(item["size"] for item in files)==manifest["total_size"] and digest==manifest["files_digest"]
    assert (len(doc.sheets),len(doc.subsets))==(manifest["sheet_count"],manifest["subset_count"]); assert all(x.layout.resolved_path for x in doc.sheets)
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
