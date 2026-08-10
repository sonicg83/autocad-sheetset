import json
import os
from pathlib import Path


def write_workspace_metadata(root: Path, workspace_id: str, dst_path: Path, revision_id: str, default_cad_version: str) -> None:
    path = root / ".dst-manager" / "workspace.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"id":workspace_id,"root":str(root),"dst_path":str(dst_path),"revision_id":revision_id,"default_cad_version":default_cad_version},ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(temp,path)
