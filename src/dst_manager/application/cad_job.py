import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from dst_manager.domain.models import JobStatus, Severity, Workspace
from dst_manager.domain.planning import build_structural_plan
from dst_manager.infrastructure.acsm_xml import AcsmDocument
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    CoreConsoleExecutor,
    ScriptRenderer,
    parse_handles,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.locking import (
    FileLockError,
    WindowsWriteLocks,
)
from dst_manager.infrastructure.filesystem.publisher import (
    PublishRecoveryError,
    PublishRolledBackError,
    RecoverablePublisher,
    file_sha256,
)
from dst_manager.infrastructure.filesystem.workspace import write_workspace_metadata
from dst_manager.infrastructure.operation_log import append_operation_event
from dst_manager.infrastructure.persistence import Database


class CadJobRunner:
    def __init__(self, database: Database, codec: DstCodec, publisher: RecoverablePublisher, timeout: int):
        self.database, self.codec, self.publisher, self.timeout = database, codec, publisher, timeout
        self.renderer, self.executor = ScriptRenderer(), CoreConsoleExecutor()

    def run(self, job: dict[str, Any], workspace: Workspace, capability: CadCapability) -> dict[str, Any]:
        job_id = job["id"]
        payload = job["payload"]
        append_operation_event(workspace.root, job_id, "WORKER_CLAIMED", cad_version=capability.version)
        if workspace.revision_id != payload["base_revision_id"]:
            self.database.update_job(job_id, JobStatus.FAILED, 0, "REVISION_CONFLICT")
            return self.database.get_job(job_id) or {}
        if not capability.available:
            self.database.update_job(job_id, JobStatus.FAILED, 0, "CAD_CAPABILITY_UNAVAILABLE")
            return self.database.get_job(job_id) or {}
        try:
            plan = build_structural_plan(workspace, payload["commands"])
            return self._execute(job_id, workspace, capability, payload["commands"], plan)
        except FileLockError:
            append_operation_event(workspace.root, job_id, "BLOCKED_FILE_LOCK")
            self.database.update_job(job_id, JobStatus.BLOCKED_FILE_LOCK, 0, "BLOCKED_FILE_LOCK")
        except PublishRolledBackError:
            append_operation_event(workspace.root, job_id, "PUBLISH_ROLLED_BACK")
            self.database.update_job(job_id, JobStatus.ROLLED_BACK, 0, "PUBLISH_ROLLED_BACK")
        except PublishRecoveryError:
            append_operation_event(workspace.root, job_id, "PUBLISH_RECOVERY_FAILED")
            self.database.update_job(job_id, JobStatus.FAILED, 0, "PUBLISH_RECOVERY_FAILED")
        except subprocess.TimeoutExpired:
            append_operation_event(workspace.root, job_id, "CAD_TIMEOUT")
            self.database.update_job(job_id, JobStatus.FAILED, 0, "CAD_TIMEOUT")
        except subprocess.CalledProcessError as exc:
            append_operation_event(workspace.root, job_id, "CAD_PROCESS_FAILED", returncode=exc.returncode)
            self._write_failure_log(workspace, job_id, exc.stdout or "", exc.stderr or "")
            self.database.update_job(job_id, JobStatus.FAILED, 0, "CAD_PROCESS_FAILED")
        except Exception as exc:  # noqa: BLE001 - Worker边界必须把任意故障持久化为终态
            append_operation_event(workspace.root, job_id, "FAILED", error=repr(exc))
            self._write_failure_log(workspace, job_id, "", repr(exc))
            self.database.update_job(job_id, JobStatus.FAILED, 0, getattr(exc, "code", type(exc).__name__.upper()))
        return self.database.get_job(job_id) or {}

    def _execute(self, job_id: str, workspace: Workspace, capability: CadCapability, commands: list[dict], plan: dict[str, Any]) -> dict[str, Any]:
        job_dir = workspace.root / ".dst-manager" / "jobs" / job_id
        staging_dir, scripts_dir, logs_dir = job_dir / "staging", job_dir / "scripts", job_dir / "logs"
        for directory in (staging_dir, scripts_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        plan_dir = workspace.root / ".dst-manager" / "revisions" / job_id / "plan"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "change-set.json").write_text(json.dumps({"base_revision_id": workspace.revision_id, "commands": commands}, ensure_ascii=False, indent=2), encoding="utf-8")
        input_dir = job_dir / "input" / "sources"
        input_dir.mkdir(parents=True, exist_ok=True)
        unique_sources = {Path(layout["source_file"]).resolve() for group in plan["groups"] for layout in group["layouts"]}
        affected_targets = {Path(group["source_target_file"]).resolve() for group in plan["groups"]} | {workspace.dst_path.resolve()}
        required_space = sum(path.stat().st_size for path in unique_sources) + 2 * sum(path.stat().st_size for path in affected_targets)
        if shutil.disk_usage(workspace.root).free < required_space:
            raise OSError("STAGING_DISK_SPACE_INSUFFICIENT")
        source_snapshots: dict[Path, Path] = {}
        for group in plan["groups"]:
            for layout in group["layouts"]:
                source = Path(layout["source_file"]).resolve()
                if source not in source_snapshots:
                    source_hash = file_sha256(source)
                    snapshot = input_dir / f"{source_hash[:16]}-{source.name}"
                    shutil.copy2(source, snapshot)
                    if file_sha256(snapshot) != source_hash or file_sha256(source) != source_hash:
                        raise ValueError(f"SOURCE_SNAPSHOT_HASH_MISMATCH: {source}")
                    source_snapshots[source] = snapshot
                layout["source_file"] = str(source_snapshots[source])
        (plan_dir / "execution-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        staged_files: dict[Path, Path | None] = {}
        bindings: dict[str, dict[str, str]] = {}
        lock_targets = [workspace.dst_path, *(Path(group["source_target_file"]) for group in plan["groups"]), *(Path(item["target_file"]) for item in plan["deleted_subsets"])]
        baseline_hashes = {path.resolve(): file_sha256(path) for path in lock_targets}
        with WindowsWriteLocks(lock_targets):
            self.database.update_job(job_id, JobStatus.CAD_RUNNING, 15)
            for group_index, group in enumerate(plan["groups"]):
                self._rebuild_group(job_id, workspace, capability, group_index, group, staging_dir, scripts_dir, logs_dir, staged_files, bindings, len(plan["groups"]))
            for deleted in plan["deleted_subsets"]:
                staged_files[Path(deleted["target_file"])] = None
            self.database.update_job(job_id, JobStatus.VERIFYING, 70)
            acsm = AcsmDocument(self.codec.decode_file(workspace.dst_path))
            acsm.apply_structural_commands(commands, workspace.revision_id)
            acsm.apply_subset_names({group["subset_id"]: group["subset_name"] for group in plan["groups"]})
            acsm.apply_layout_bindings(bindings, workspace.root)
            issues = acsm.validate()
            if any(issue.severity == Severity.ERROR for issue in issues):
                raise ValueError("XML_VALIDATION_FAILED")
            staged_dst = staging_dir / workspace.dst_path.name
            self.codec.encode_file(acsm.to_bytes(), staged_dst)
            roundtrip = AcsmDocument(self.codec.decode_file(staged_dst))
            if roundtrip.semantic_bytes() != acsm.semantic_bytes():
                raise ValueError("DST_ROUNDTRIP_MISMATCH")
            staged_files[workspace.dst_path] = staged_dst
            self.database.update_job(job_id, JobStatus.PREPARED, 80)
            for path, expected_hash in baseline_hashes.items():
                if file_sha256(path) != expected_hash:
                    raise ValueError(f"BASE_FILE_CHANGED: {path}")
        before_hash = baseline_hashes[workspace.dst_path.resolve()]
        self.database.update_job(job_id, JobStatus.PUBLISHING, 90)
        append_operation_event(workspace.root, job_id, "PUBLISHING", file_count=len(staged_files))
        revision_dir = self.publisher.publish(job_id, workspace.root, staged_files)
        result_hash = file_sha256(workspace.dst_path)
        append_operation_event(workspace.root, job_id, "SUCCEEDED", revision_id=result_hash)
        shutil.copytree(logs_dir, revision_dir / "logs", dirs_exist_ok=True)
        shutil.copytree(scripts_dir, revision_dir / "scripts", dirs_exist_ok=True)
        shutil.copytree(input_dir.parent, revision_dir / "input", dirs_exist_ok=True)
        self.database.add_revision(result_hash, workspace.id, job_id, before_hash, result_hash, revision_dir)
        write_workspace_metadata(workspace.root, workspace.id, workspace.dst_path, result_hash, capability.version)
        self.database.update_job(job_id, JobStatus.SUCCEEDED, 100)
        return self.database.get_job(job_id) or {}

    def _rebuild_group(self, job_id: str, workspace: Workspace, capability: CadCapability, group_index: int, group: dict, staging_dir: Path, scripts_dir: Path, logs_dir: Path, staged_files: dict[Path, Path | None], bindings: dict[str, dict[str, str]], group_count: int) -> None:
        source_target = Path(group["source_target_file"])
        target = Path(group["target_file"])
        group_dir = staging_dir / f"group-{group_index:03d}"
        group_dir.mkdir(parents=True, exist_ok=True)
        staged = group_dir / target.name
        shutil.copy2(source_target, staged)
        rebuild_script = scripts_dir / f"rebuild-{group_index:03d}.scr"
        rebuild_script.write_text(self.renderer.render_rebuild(capability.plugin, group["layouts"]), encoding="mbcs")
        completed = self.executor.run(capability, staged, rebuild_script, self.timeout)
        (logs_dir / f"rebuild-{group_index:03d}.log").write_text((completed.stdout or "") + (completed.stderr or ""), encoding="utf-8")
        handle_script = scripts_dir / f"handles-{group_index:03d}.scr"
        handle_script.write_text(self.renderer.render_handles(capability.plugin), encoding="mbcs")
        completed = self.executor.run(capability, staged, handle_script, self.timeout)
        (logs_dir / f"handles-{group_index:03d}.log").write_text((completed.stdout or "") + (completed.stderr or ""), encoding="utf-8")
        handle_path = staged.with_suffix(".dst-handles.txt")
        handles = parse_handles(handle_path.read_text(encoding="utf-8"))
        expected = {layout["target_layout"] for layout in group["layouts"]}
        if set(handles) != expected:
            raise ValueError(f"HANDLE_LAYOUT_MISMATCH: expected={sorted(expected)!r}, actual={sorted(handles)!r}")
        for layout in group["layouts"]:
            bindings[layout["sheet_id"]] = {"file": str(target), "layout": layout["target_layout"], "handle": handles[layout["target_layout"]]}
        if source_target.resolve() != target.resolve():
            staged_files[source_target] = None
        staged_files[target] = staged
        self.database.update_job(job_id, JobStatus.CAD_RUNNING, 15 + int(50 * (group_index + 1) / max(1, group_count)))

    @staticmethod
    def _write_failure_log(workspace: Workspace, job_id: str, stdout: str, stderr: str) -> None:
        path = workspace.root / ".dst-manager" / "jobs" / job_id / "logs" / "failure.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stdout + "\n" + stderr, encoding="utf-8")
