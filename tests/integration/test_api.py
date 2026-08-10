from fastapi.testclient import TestClient

from dst_manager.config import Settings
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.interfaces.api import create_app


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
