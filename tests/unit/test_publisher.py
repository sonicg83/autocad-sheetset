import json
import os
from pathlib import Path

import pytest

from dst_manager.infrastructure.filesystem.locking import WindowsWriteLocks
from dst_manager.infrastructure.filesystem.publisher import (
    PublishRolledBackError,
    RecoverablePublisher,
)


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_publish_failure_rolls_back_every_replaced_file(tmp_path: Path, fail_at: int):
    targets = {}
    for index in range(3):
        target = tmp_path / f"target-{index}.txt"
        source = tmp_path / f"staged-{index}.txt"
        target.write_text(f"before-{index}")
        source.write_text(f"after-{index}")
        targets[target] = source
    calls = 0

    def replace(source: Path, target: Path):
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise OSError("注入发布故障")
        os.replace(source, target)

    with pytest.raises(PublishRolledBackError, match="注入发布故障"):
        RecoverablePublisher(replace).publish("fault", tmp_path, targets)
    assert [path.read_text() for path in targets] == ["before-0", "before-1", "before-2"]
    journal = json.loads((tmp_path / ".dst-manager/jobs/fault/publish-journal.json").read_text(encoding="utf-8"))
    assert journal["status"] == "ROLLED_BACK"
    assert all((tmp_path / ".dst-manager/revisions/fault/before" / path.name).is_file() for path in targets)


def test_deleted_file_is_restored_when_later_publish_fails(tmp_path: Path):
    deleted, replaced, staged = tmp_path / "delete.txt", tmp_path / "replace.txt", tmp_path / "staged.txt"
    deleted.write_text("keep-delete"); replaced.write_text("keep-replace"); staged.write_text("new")
    def fail(*_): raise OSError("fail")
    # 删除项先执行，第二项替换失败。
    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(fail).publish("delete-fault", tmp_path, {deleted: None, replaced: staged})
    assert deleted.read_text() == "keep-delete" and replaced.read_text() == "keep-replace"


@pytest.mark.parametrize("status", ["PREPARED", "PUBLISHING", "ROLLING_BACK"])
def test_startup_recovery_closes_unfinished_journal(tmp_path: Path, status: str):
    operation="crash"; target=tmp_path/"target.txt"; target.write_text("after")
    backup=tmp_path/".dst-manager"/"revisions"/operation/"before"/target.name; backup.parent.mkdir(parents=True); backup.write_text("before")
    journal_path=tmp_path/".dst-manager"/"jobs"/operation/"publish-journal.json"; journal_path.parent.mkdir(parents=True)
    journal={"operation_id":operation,"status":status,"files":[{"target":str(target),"backup":str(backup),"staged":None,"replaced":status!="PREPARED"}]}; journal_path.write_text(json.dumps(journal),encoding="utf-8")
    assert RecoverablePublisher().recover(tmp_path)==[operation]
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"]=="ROLLED_BACK"
    assert target.read_text()==("after" if status=="PREPARED" else "before")


def test_windows_lock_blocks_writers_but_allows_readers(tmp_path: Path):
    target=tmp_path/"locked.txt"; target.write_text("data")
    with WindowsWriteLocks([target]):
        assert target.read_text()=="data"
        with pytest.raises(PermissionError): target.write_text("changed")
    target.write_text("changed"); assert target.read_text()=="changed"
