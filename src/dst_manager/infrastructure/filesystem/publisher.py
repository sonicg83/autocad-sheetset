import hashlib
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class PublishRolledBackError(RuntimeError):
    code = "PUBLISH_ROLLED_BACK"


class PublishRecoveryError(RuntimeError):
    code = "PUBLISH_RECOVERY_FAILED"


class RecoverablePublisher:
    """以before快照和同步日志提供多文件可恢复发布。"""

    def __init__(self, replace_file: Callable[[Path, Path], None] | None = None):
        self._replace_file = replace_file or os.replace

    def publish(self, operation_id: str, workspace_root: Path, staged: dict[Path, Path | None]) -> Path:
        manager_dir = workspace_root / ".dst-manager"
        revision_dir = manager_dir / "revisions" / operation_id
        before_dir = revision_dir / "before"
        journal_path = manager_dir / "jobs" / operation_id / "publish-journal.json"
        before_dir.mkdir(parents=True, exist_ok=False)
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        for target, staged_file in staged.items():
            target = target.resolve()
            if workspace_root.resolve() not in target.parents:
                raise ValueError(f"PUBLISH_OUTSIDE_WORKSPACE: {target}")
            target_existed = target.exists()
            backup = before_dir / target.relative_to(workspace_root.resolve())
            if target_existed:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            elif staged_file is None:
                raise FileNotFoundError(f"DELETE_TARGET_NOT_FOUND: {target}")
            entries.append({"target": str(target), "staged": str(staged_file) if staged_file else None, "backup": str(backup) if target_existed else None, "before_hash": file_sha256(target) if target_existed else None, "replaced": False})
        journal = {"operation_id": operation_id, "status": "PREPARED", "files": entries}
        self._write_journal(journal_path, journal)
        try:
            journal["status"] = "PUBLISHING"
            self._write_journal(journal_path, journal)
            for entry in entries:
                target = Path(entry["target"])
                if entry["staged"] is None:
                    target.unlink()
                else:
                    staged_file = Path(entry["staged"])
                    publish_temp = target.with_name(f".{target.name}.{operation_id}.tmp")
                    shutil.copy2(staged_file, publish_temp)
                    self._replace_file(publish_temp, target)
                entry["replaced"] = True
                entry["result_hash"] = file_sha256(target) if target.exists() else None
                self._write_journal(journal_path, journal)
            journal["status"] = "COMMITTED"
            self._write_journal(journal_path, journal)
            (revision_dir / "manifest.json").write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
            shutil.copy2(journal_path, revision_dir / "publish-journal.json")
            return revision_dir
        except Exception as publish_error:
            journal["status"] = "ROLLING_BACK"
            self._write_journal(journal_path, journal)
            try:
                for entry in reversed(entries):
                    if entry["replaced"]:
                        target = Path(entry["target"])
                        if entry["backup"] is None:
                            target.unlink(missing_ok=True)
                        else:
                            backup = Path(entry["backup"])
                            restore_temp = target.with_name(f".{target.name}.{operation_id}.restore")
                            shutil.copy2(backup, restore_temp)
                            os.replace(restore_temp, target)
                journal["status"] = "ROLLED_BACK"
                self._write_journal(journal_path, journal)
            except Exception as recovery_error:  # noqa: BLE001 - 任何恢复故障都必须进入可再次恢复状态
                journal["status"] = "ROLLBACK_FAILED"
                self._write_journal(journal_path, journal)
                raise PublishRecoveryError(str(recovery_error)) from publish_error
            raise PublishRolledBackError(str(publish_error)) from publish_error

    @staticmethod
    def _write_journal(path: Path, journal: dict) -> None:
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)

    def recover(self, workspace_root: Path) -> list[str]:
        recovered: list[str] = []
        jobs = workspace_root / ".dst-manager" / "jobs"
        if not jobs.exists():
            return recovered
        for path in jobs.glob("*/publish-journal.json"):
            journal = json.loads(path.read_text(encoding="utf-8"))
            if journal["status"] in {"COMMITTED", "ROLLED_BACK"}:
                continue
            for entry in reversed(journal["files"]):
                if entry.get("replaced"):
                    target = Path(entry["target"])
                    if entry.get("backup") is None:
                        target.unlink(missing_ok=True)
                    elif Path(entry["backup"]).exists():
                        backup = Path(entry["backup"])
                        restore_temp = target.with_name(f".{target.name}.{journal['operation_id']}.restore")
                        shutil.copy2(backup, restore_temp)
                        os.replace(restore_temp, target)
            journal["status"] = "ROLLED_BACK"
            self._write_journal(path, journal)
            recovered.append(journal["operation_id"])
        return recovered
