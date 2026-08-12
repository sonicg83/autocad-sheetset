from fastapi.testclient import TestClient

from dst_manager.config import Settings
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.interfaces.api import create_app


def test_read_only_open_does_not_create_workspace_metadata(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    data_dir = tmp_path / "application-data"
    client = TestClient(create_app(Settings(data_dir=data_dir)))
    response = client.post("/api/workspaces/open", json={"dst_path": str(dst)})
    assert response.status_code == 200
    assert not (tmp_path / ".dst-manager").exists()


def test_open_preview_execute(tmp_path,tiny_workspace):
    dst,sheet_id=tiny_workspace; client=TestClient(create_app(Settings(data_dir=tmp_path/"data"))); opened=client.post("/api/workspaces/open",json={"dst_path":str(dst)}).json(); assert opened["sheet_set"]["sheet_count"]==1
    payload={"base_revision_id":opened["revision_id"],"commands":[{"type":"update_sheet","sheet_id":sheet_id,"custom_properties":{"比例":"1:200"}}]}; assert client.post(f"/api/workspaces/{opened['id']}/changes/preview",json=payload).json()["requires_cad"] is False
    job=client.post(f"/api/workspaces/{opened['id']}/changes/execute",json=payload).json(); assert job["status"]=="SUCCEEDED"; assert (dst.parent/".dst-manager"/"revisions"/job["id"]/"before"/dst.name).is_file()
def test_revision_conflict(tmp_path,tiny_workspace):
    dst,_=tiny_workspace; client=TestClient(create_app(Settings(data_dir=tmp_path/"data"))); opened=client.post("/api/workspaces/open",json={"dst_path":str(dst)}).json(); response=client.post(f"/api/workspaces/{opened['id']}/changes/preview",json={"base_revision_id":"stale","commands":[]}); assert response.status_code==409 and response.json()["code"]=="REVISION_CONFLICT"

def test_sheet_set_name_is_metadata_only(tmp_path,tiny_workspace):
    dst,_=tiny_workspace; client=TestClient(create_app(Settings(data_dir=tmp_path/"data"))); opened=client.post("/api/workspaces/open",json={"dst_path":str(dst)}).json(); payload={"base_revision_id":opened["revision_id"],"commands":[{"type":"update_sheet_set","name":"新图纸集"}]}
    assert client.post(f"/api/workspaces/{opened['id']}/changes/preview",json=payload).json()["requires_cad"] is False
    assert client.post(f"/api/workspaces/{opened['id']}/changes/execute",json=payload).json()["status"]=="SUCCEEDED"

def test_xml_preview_and_export_are_revisioned(tmp_path,tiny_workspace):
    dst,_=tiny_workspace; client=TestClient(create_app(Settings(data_dir=tmp_path/"data"))); opened=client.post("/api/workspaces/open",json={"dst_path":str(dst)}).json(); xml=DstCodec().decode_file(dst).decode().replace("平面</AcSmProp>","导入标题</AcSmProp>")
    payload={"base_revision_id":opened["revision_id"],"xml":xml}
    preview=client.post(f"/api/workspaces/{opened['id']}/xml/import/preview",json=payload).json(); assert any(item["type"]=="sheet_changed" for item in preview["changes"])
    destination=tmp_path/"export.dst"; payload["destination"]=str(destination); job=client.post(f"/api/workspaces/{opened['id']}/xml/export-dst",json=payload).json(); assert job["status"]=="SUCCEEDED" and destination.is_file()
    assert (tmp_path/".dst-manager"/"revisions"/job["id"]).is_dir()


def test_revision_restore_creates_new_revision_and_keeps_history(tmp_path, tiny_workspace):
    dst, sheet_id = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {"base_revision_id": opened["revision_id"], "commands": [{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": "1:200"}}]}
    changed = client.post(f"/api/workspaces/{opened['id']}/changes/execute", json=payload).json()
    assert changed["status"] == "SUCCEEDED"
    revision = client.get("/api/revisions", params={"workspace_id": opened["id"]}).json()[0]
    current = client.get(f"/api/workspaces/{opened['id']}").json()
    preview = client.get(f"/api/workspaces/{opened['id']}/revisions/{revision['id']}/restore-preview").json()
    assert preview["executable"] is True
    assert preview["files"] == [preview["files"][0] | {"path": dst.name, "action": "replace", "conflict": False}]
    restored = client.post(
        f"/api/workspaces/{opened['id']}/revisions/{revision['id']}/restore",
        json={"base_revision_id": current["revision_id"]},
    ).json()
    assert restored["status"] == "SUCCEEDED"
    reopened = client.get(f"/api/workspaces/{opened['id']}").json()
    assert reopened["sheet_set"]["subsets"][0]["sheets"][0]["custom_properties"]["比例"] == "1:100"
    revisions = client.get("/api/revisions", params={"workspace_id": opened["id"]}).json()
    assert len(revisions) == 2
    restore_revision = next(item for item in revisions if item["id"].startswith("restore-"))
    reverse_preview = client.get(f"/api/workspaces/{opened['id']}/revisions/{restore_revision['id']}/restore-preview").json()
    assert reverse_preview["executable"] is True
    reversed_job = client.post(
        f"/api/workspaces/{opened['id']}/revisions/{restore_revision['id']}/restore",
        json={"base_revision_id": reopened["revision_id"]},
    ).json()
    assert reversed_job["status"] == "SUCCEEDED"
    changed_again = client.get(f"/api/workspaces/{opened['id']}").json()
    assert changed_again["sheet_set"]["subsets"][0]["sheets"][0]["custom_properties"]["比例"] == "1:200"


def test_revision_restore_rejects_changed_current_file(tmp_path, tiny_workspace):
    dst, sheet_id = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {"base_revision_id": opened["revision_id"], "commands": [{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": "1:200"}}]}
    client.post(f"/api/workspaces/{opened['id']}/changes/execute", json=payload)
    revision = client.get("/api/revisions", params={"workspace_id": opened["id"]}).json()[0]
    dst.write_bytes(dst.read_bytes() + b"external-change")
    preview = client.get(f"/api/workspaces/{opened['id']}/revisions/{revision['id']}/restore-preview").json()
    assert preview["executable"] is False
    assert preview["conflicts"] == [dst.name]
