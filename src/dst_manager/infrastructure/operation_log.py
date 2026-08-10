import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def append_operation_event(workspace_root: Path, operation_id: str, event: str, **data: Any) -> None:
    path=workspace_root/".dst-manager"/"jobs"/operation_id/"logs"/"events.jsonl"; path.parent.mkdir(parents=True,exist_ok=True)
    record={"timestamp":datetime.now(UTC).isoformat(),"operation_id":operation_id,"event":event,**data}
    with path.open("a",encoding="utf-8") as stream: stream.write(json.dumps(record,ensure_ascii=False,default=str)+"\n")
