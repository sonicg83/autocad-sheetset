import json
import shutil
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
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
from dst_manager.infrastructure.logging_text import sanitize_log_text
from dst_manager.infrastructure.operation_log import append_operation_event
from dst_manager.infrastructure.persistence import Database


@dataclass(frozen=True, slots=True)
class RebuildWorkUnit:
    index: int
    group: dict[str, Any]
    source_snapshot: Path
    staging_dir: Path
    scripts_dir: Path
    logs_dir: Path
    timeout: int


@dataclass(frozen=True, slots=True)
class RebuildResult:
    index: int
    target: Path
    source_target: Path
    staged: Path
    bindings: dict[str, dict[str, str]]
    duration_ms: int
    log_path: Path
    peak_memory_bytes: int | None
    staging_bytes: int


class CadJobRunner:
    def __init__(self, database: Database, codec: DstCodec, publisher: RecoverablePublisher, timeout: int, max_parallel: int = 2):
        self.database, self.codec, self.publisher, self.timeout = database, codec, publisher, timeout
        if not 1 <= max_parallel <= 4:
            raise ValueError("CAD_MAX_PARALLEL_OUT_OF_RANGE")
        self.max_parallel = max_parallel
        self.renderer, self.executor = ScriptRenderer(), CoreConsoleExecutor()

    def run(self, job: dict[str, Any], workspace: Workspace, capability: CadCapability) -> dict[str, Any]:
        job_id = job["id"]
        payload = job["payload"]
        worker_id = job.get("worker_id") or "local-worker"
        append_operation_event(workspace.root, job_id, "WORKER_CLAIMED", cad_version=capability.version)
        if workspace.revision_id != payload["base_revision_id"]:
            self.database.update_job(job_id, JobStatus.FAILED, 0, "REVISION_CONFLICT")
            return self.database.get_job(job_id) or {}
        if not capability.available:
            self.database.update_job(job_id, JobStatus.FAILED, 0, "CAD_CAPABILITY_UNAVAILABLE")
            return self.database.get_job(job_id) or {}
        try:
            plan = build_structural_plan(workspace, payload["commands"])
            return self._execute(job_id, worker_id, job.get("attempt", 1), workspace, capability, payload["commands"], plan)
        except FileLockError as exc:
            append_operation_event(workspace.root, job_id, "BLOCKED_FILE_LOCK")
            self.database.update_job(job_id, JobStatus.BLOCKED_FILE_LOCK, 0, "BLOCKED_FILE_LOCK", str(exc))
        except PublishRolledBackError as exc:
            append_operation_event(workspace.root, job_id, "PUBLISH_ROLLED_BACK")
            self.database.update_job(job_id, JobStatus.ROLLED_BACK, 0, "PUBLISH_ROLLED_BACK", str(exc))
        except PublishRecoveryError as exc:
            append_operation_event(workspace.root, job_id, "PUBLISH_RECOVERY_FAILED")
            self.database.update_job(job_id, JobStatus.FAILED, 0, "PUBLISH_RECOVERY_FAILED", str(exc))
        except subprocess.TimeoutExpired as exc:
            append_operation_event(workspace.root, job_id, "CAD_TIMEOUT")
            self.database.update_job(job_id, JobStatus.FAILED, 0, "CAD_TIMEOUT", str(exc))
        except subprocess.CalledProcessError as exc:
            append_operation_event(workspace.root, job_id, "CAD_PROCESS_FAILED", returncode=exc.returncode)
            self._write_failure_log(workspace, job_id, job.get("attempt", 1), exc.stdout or "", exc.stderr or "")
            self.database.update_job(job_id, JobStatus.FAILED, 0, "CAD_PROCESS_FAILED", str(exc))
        except Exception as exc:  # noqa: BLE001 - Worker边界必须把任意故障持久化为终态
            append_operation_event(workspace.root, job_id, "FAILED", error=repr(exc))
            self._write_failure_log(workspace, job_id, job.get("attempt", 1), "", repr(exc))
            self.database.update_job(job_id, JobStatus.FAILED, 0, getattr(exc, "code", type(exc).__name__.upper()), str(exc))
        return self.database.get_job(job_id) or {}

    def _execute(self, job_id: str, worker_id: str, attempt: int, workspace: Workspace, capability: CadCapability, commands: list[dict], plan: dict[str, Any]) -> dict[str, Any]:
        job_dir = workspace.root / ".dst-manager" / "jobs" / job_id
        attempt_dir = job_dir / f"attempt-{attempt:03d}"
        staging_dir, scripts_dir, logs_dir = attempt_dir / "staging", attempt_dir / "scripts", attempt_dir / "logs"
        for directory in (staging_dir, scripts_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        plan_dir = workspace.root / ".dst-manager" / "revisions" / job_id / "plan"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "change-set.json").write_text(json.dumps({"base_revision_id": workspace.revision_id, "commands": commands}, ensure_ascii=False, indent=2), encoding="utf-8")
        input_dir = attempt_dir / "input" / "sources"
        input_dir.mkdir(parents=True, exist_ok=True)
        unique_sources = {Path(layout["source_file"]).resolve() for group in plan["groups"] for layout in group["layouts"]}
        unique_sources.update(Path(group["source_target_file"]).resolve() for group in plan["groups"])
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
            group["source_snapshot"] = str(source_snapshots[Path(group["source_target_file"]).resolve()])
        (plan_dir / "execution-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        staged_files: dict[Path, Path | None] = {}
        bindings: dict[str, dict[str, str]] = {}
        publication_targets = [workspace.dst_path, *(Path(group["source_target_file"]) for group in plan["groups"]), *(Path(group["target_file"]) for group in plan["groups"]), *(Path(item["target_file"]) for item in plan["deleted_subsets"])]
        baseline_hashes = {path.resolve(): file_sha256(path) if path.exists() else None for path in publication_targets}
        lock_targets = [path for path in publication_targets if path.exists()]
        with WindowsWriteLocks(lock_targets):
            self.database.update_job(job_id, JobStatus.CAD_RUNNING, 15)
            units = [RebuildWorkUnit(index, group, Path(group["source_snapshot"]), staging_dir, scripts_dir, logs_dir, self.timeout) for index, group in enumerate(plan["groups"])]
            results = self._run_groups(job_id, worker_id, workspace, capability, units)
            for result in sorted(results, key=lambda item: item.index):
                bindings.update(result.bindings)
                if result.source_target.resolve() != result.target.resolve():
                    staged_files[result.source_target] = None
                staged_files[result.target] = result.staged
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
                current_hash = file_sha256(path) if path.exists() else None
                if current_hash != expected_hash:
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

    def _run_groups(self, job_id: str, worker_id: str, workspace: Workspace, capability: CadCapability, units: list[RebuildWorkUnit]) -> list[RebuildResult]:
        if not units:
            return []
        results: list[RebuildResult] = []
        next_index = 0
        failed: BaseException | None = None
        futures: dict[Future[RebuildResult], RebuildWorkUnit] = {}
        with ThreadPoolExecutor(max_workers=self.max_parallel, thread_name_prefix="dst-cad") as pool:
            while next_index < len(units) and len(futures) < self.max_parallel:
                unit = units[next_index]
                futures[pool.submit(self._rebuild_group, job_id, workspace, capability, unit)] = unit
                next_index += 1
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    unit = futures.pop(future)
                    try:
                        results.append(future.result())
                    except BaseException as exc:  # noqa: BLE001 - 等待已启动 CAD 安全退出后统一抛出
                        failed = failed or exc
                    completed = len(results)
                    self.database.update_job(job_id, JobStatus.CAD_RUNNING, 15 + int(50 * completed / len(units)))
                    self.database.heartbeat(job_id, worker_id)
                    if failed is None and next_index < len(units):
                        following = units[next_index]
                        futures[pool.submit(self._rebuild_group, job_id, workspace, capability, following)] = following
                        next_index += 1
                if failed is not None:
                    for future in futures:
                        future.cancel()
        if failed is not None:
            raise failed
        return results

    def _rebuild_group(self, job_id: str, workspace: Workspace, capability: CadCapability, unit: RebuildWorkUnit) -> RebuildResult:
        group_index, group = unit.index, unit.group
        source_target = Path(group["source_target_file"])
        target = Path(group["target_file"])
        started = time.perf_counter()
        group_dir = unit.staging_dir / f"group-{group_index:03d}"
        group_dir.mkdir(parents=True, exist_ok=True)
        staged = group_dir / target.name
        shutil.copy2(unit.source_snapshot, staged)
        rebuild_script = unit.scripts_dir / f"rebuild-{group_index:03d}.scr"
        log_path = unit.logs_dir / f"group-{group_index:03d}.log"
        self.database.upsert_job_file(job_id, target, source_path=str(source_target), status="RUNNING", progress=5, log_path=str(log_path), before_hash=file_sha256(source_target))
        rebuild_script.write_text(self.renderer.render_rebuild(capability.plugin, group["layouts"]), encoding="mbcs")
        output = ""
        phase = "重建布局"
        try:
            completed = self.executor.run(capability, staged, rebuild_script, unit.timeout)
            peak_memory = completed.peak_memory_bytes
            output += self._format_console_output(phase, completed.stdout, completed.stderr)
            handle_script = unit.scripts_dir / f"handles-{group_index:03d}.scr"
            handle_script.write_text(self.renderer.render_handles(capability.plugin), encoding="mbcs")
            phase = "读取布局 Handle"
            completed = self.executor.run(capability, staged, handle_script, unit.timeout)
            peak_memory = max(value for value in (peak_memory, completed.peak_memory_bytes) if value is not None) if any(value is not None for value in (peak_memory, completed.peak_memory_bytes)) else None
            output += self._format_console_output(phase, completed.stdout, completed.stderr)
            log_path.write_text(sanitize_log_text(output), encoding="utf-8")
            handles = parse_handles(staged.with_suffix(".dst-handles.txt").read_text(encoding="utf-8"))
            expected = {layout["target_layout"] for layout in group["layouts"]}
            if set(handles) != expected:
                raise ValueError(f"HANDLE_LAYOUT_MISMATCH: expected={sorted(expected)!r}, actual={sorted(handles)!r}")
            bindings = {layout["sheet_id"]: {"file": str(target), "layout": layout["target_layout"], "handle": handles[layout["target_layout"]]} for layout in group["layouts"]}
            duration_ms = int((time.perf_counter() - started) * 1000)
            staging_bytes = staged.stat().st_size
            self.database.upsert_job_file(job_id, target, status="SUCCEEDED", progress=100, duration_ms=duration_ms, peak_memory_bytes=peak_memory, staging_bytes=staging_bytes, result_hash=file_sha256(staged))
            return RebuildResult(group_index, target, source_target, staged, bindings, duration_ms, log_path, peak_memory, staging_bytes)
        except Exception as exc:
            if isinstance(exc, subprocess.CalledProcessError):
                stdout = exc.stdout if exc.stdout is not None else exc.output
                output += self._format_console_output(phase, stdout, exc.stderr, exc.returncode)
            duration_ms = int((time.perf_counter() - started) * 1000)
            log_path.write_text(sanitize_log_text(output + "\n" + repr(exc)), encoding="utf-8")
            self.database.upsert_job_file(job_id, target, status="FAILED", progress=0, duration_ms=duration_ms, error_code=getattr(exc, "code", type(exc).__name__.upper()), error_detail=str(exc))
            raise

    @staticmethod
    def _format_console_output(phase: str, stdout: str | bytes | None, stderr: str | bytes | None, returncode: int = 0) -> str:
        """将每次 Core Console 调用的两个输出流完整归档，并标记所属阶段。"""
        def text(value: str | bytes | None) -> str:
            if value is None:
                return ""
            if isinstance(value, bytes):
                return value.decode("mbcs", errors="replace")
            return value

        return (
            f"\n===== Core Console：{phase}（退出码 {returncode}）stdout =====\n{text(stdout)}"
            f"\n===== Core Console：{phase}（退出码 {returncode}）stderr =====\n{text(stderr)}\n"
        )

    @staticmethod
    def _write_failure_log(workspace: Workspace, job_id: str, attempt: int, stdout: str, stderr: str) -> None:
        path = workspace.root / ".dst-manager" / "jobs" / job_id / f"attempt-{attempt:03d}" / "logs" / "failure.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sanitize_log_text(stdout + "\n" + stderr), encoding="utf-8")
