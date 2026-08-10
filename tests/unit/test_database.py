from pathlib import Path

import pytest

from dst_manager.infrastructure.persistence.database import Database, WorkspaceBusyError


def test_workspace_allows_only_one_active_write_job(tmp_path: Path):
    database=Database(f"sqlite:///{(tmp_path/'db.sqlite').as_posix()}"); root=tmp_path/"project"; root.mkdir(); dst=root/"a.dst"; dst.write_bytes(b"x"); database.upsert_workspace("w",root,dst,"rev")
    database.create_job("job-1","w","change_set","QUEUED",{})
    with pytest.raises(WorkspaceBusyError): database.create_job("job-2","w","change_set","QUEUED",{})
    database.update_job("job-1","FAILED",0,"TEST")
    database.create_job("job-2","w","change_set","QUEUED",{})
