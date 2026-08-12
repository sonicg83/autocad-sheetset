import json
import re
import shutil
import socket
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dst_manager.application.cad_job import CadJobRunner
from dst_manager.config import Settings
from dst_manager.domain.models import JobStatus, Severity, Workspace
from dst_manager.domain.planning import PlanningError, build_structural_plan
from dst_manager.infrastructure.acsm_xml import AcsmDocument, AcsmValidationError
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    CoreConsoleExecutor,
    ScriptRenderer,
    parse_handles,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.publisher import (
    PublishRolledBackError,
    RecoverablePublisher,
    file_sha256,
)
from dst_manager.infrastructure.filesystem.workspace import write_workspace_metadata
from dst_manager.infrastructure.operation_log import append_operation_event
from dst_manager.infrastructure.persistence import Database
from dst_manager.infrastructure.persistence.database import WorkspaceBusyError


class ApplicationError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code, self.status_code = code, status_code


class DstManagerService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.database = Database(self.settings.database_url)
        self.codec = DstCodec()
        self.publisher = RecoverablePublisher()
        for root in self.database.list_workspace_roots():
            for operation_id in self.publisher.recover(root):
                try:
                    self.database.update_job(operation_id, JobStatus.ROLLED_BACK, 0, "STARTUP_RECOVERY")
                except KeyError:
                    pass
        self.database.recover_stale_jobs(self.settings.worker_lease_seconds)

    def open_workspace(self, dst_path: Path, root_override: Path | None = None) -> Workspace:
        dst_path = dst_path.expanduser().resolve()
        if dst_path.suffix.lower() != ".dst" or not dst_path.is_file():
            raise ApplicationError("DST_NOT_FOUND", f"DST文件不存在：{dst_path}", 404)
        root = dst_path.parent
        self.publisher.recover(root)
        revision = file_sha256(dst_path)
        workspace_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(dst_path).casefold()))
        acsm = AcsmDocument(self.codec.decode_file(dst_path))
        document = acsm.project(root, root_override)
        referenced = {sheet.layout.resolved_path for sheet in document.sheets if sheet.layout.resolved_path}
        unreferenced = sorted((path.resolve() for path in root.glob("*.dwg") if path.resolve() not in referenced), key=str)
        if unreferenced:
            document.diagnostics.append(self._issue("UNREFERENCED_DWG", "info", f"发现{len(unreferenced)}个未引用DWG"))
        workspace = Workspace(workspace_id, root, dst_path, revision, document, unreferenced)
        self.database.upsert_workspace(workspace_id, root, dst_path, revision, root_override)
        return workspace

    def get_workspace(self, workspace_id: str) -> Workspace:
        row = self.database.get_workspace(workspace_id)
        if row is None:
            raise ApplicationError("WORKSPACE_NOT_FOUND", "工作区不存在", 404)
        return self.open_workspace(Path(row.dst_path), Path(row.root_override) if row.root_override else None)

    def preview_changes(self, workspace_id: str, base_revision_id: str, commands: list[dict[str, Any]]) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        known = {"update_sheet_set", "update_subset", "update_sheet", "delete_sheet", "move_sheet", "reorder_sheet", "insert_sheet", "renumber_sheets"}
        invalid = [command.get("type") for command in commands if command.get("type") not in known]
        if invalid:
            raise ApplicationError("COMMAND_UNSUPPORTED", f"不支持的命令：{invalid}")
        sheet_ids = {sheet.acsm_id for sheet in workspace.document.sheets}
        diagnostics = []
        changes = []
        structural = False
        for index, command in enumerate(commands):
            command_type = command["type"]
            sheet_id = command.get("sheet_id")
            if command_type in {"update_sheet", "delete_sheet", "move_sheet", "reorder_sheet"} and sheet_id not in sheet_ids:
                diagnostics.append({"code": "SHEET_NOT_FOUND", "severity": "error", "message": f"找不到图纸：{sheet_id}", "index": index})
            if command_type == "insert_sheet" and not command.get("source"):
                diagnostics.append({"code": "LAYOUT_SOURCE_REQUIRED", "severity": "error", "message": "新增图纸必须明确布局来源", "index": index})
            structural |= command_type in {"delete_sheet", "move_sheet", "reorder_sheet", "insert_sheet", "renumber_sheets"} or (command_type == "update_sheet" and ("number" in command or "title" in command))
            changes.append({"index": index, "type": command_type, "object_id": sheet_id, "after": command})
        execution_intent = None
        if structural and not diagnostics:
            try:
                execution_intent = build_structural_plan(workspace, commands)
            except PlanningError as exc:
                diagnostics.append({"code": exc.code, "severity": "error", "message": str(exc)})
        affected = {str(workspace.dst_path)}
        if execution_intent:
            affected.update(group["target_file"] for group in execution_intent["groups"])
            affected.update(group["source_target_file"] for group in execution_intent["groups"])
            affected.update(item["target_file"] for item in execution_intent["deleted_subsets"])
        return {"workspace_id": workspace_id, "base_revision_id": base_revision_id, "requires_cad": structural, "affected_files": sorted(affected), "execution_intent": execution_intent, "changes": changes, "diagnostics": diagnostics, "executable": not any(item["severity"] == "error" for item in diagnostics)}

    def execute_changes(self, workspace_id: str, base_revision_id: str, commands: list[dict[str, Any]], cad_version: str = "2020") -> dict[str, Any]:
        plan = self.preview_changes(workspace_id, base_revision_id, commands)
        if not plan["executable"]:
            raise ApplicationError("PLAN_INVALID", "执行计划包含阻断诊断")
        job_id = str(uuid.uuid4())
        try:
            self.database.create_job(job_id, workspace_id, "change_set", JobStatus.VALIDATED, {"base_revision_id": base_revision_id, "plan": plan, "commands": commands}, cad_version)
        except WorkspaceBusyError as exc:
            raise ApplicationError("WORKSPACE_WRITE_BUSY", str(exc), 409) from exc
        if plan["requires_cad"]:
            capability = self.capabilities()[cad_version]
            if capability["available"]:
                self.database.update_job(job_id, JobStatus.QUEUED, 0)
            else:
                self.database.update_job(job_id, JobStatus.FAILED, 0, "CAD_CAPABILITY_UNAVAILABLE")
            return self.database.get_job(job_id) or {}
        workspace = self.get_workspace(workspace_id)
        operation_id = job_id
        self._write_workspace_file(workspace)
        self.database.update_job(job_id, JobStatus.STAGING, 20)
        append_operation_event(workspace.root, job_id, "STAGING", job_type="metadata")
        acsm = AcsmDocument(self.codec.decode_file(workspace.dst_path))
        try:
            acsm.apply_metadata_commands(commands)
        except AcsmValidationError as exc:
            self.database.update_job(job_id, JobStatus.FAILED, 0, str(exc).split(":", 1)[0])
            return self.database.get_job(job_id) or {}
        issues = acsm.validate()
        if any(issue.severity == Severity.ERROR for issue in issues):
            self.database.update_job(job_id, JobStatus.FAILED, 0, "XML_VALIDATION_FAILED")
            return self.database.get_job(job_id) or {}
        job_dir = workspace.root / ".dst-manager" / "jobs" / operation_id
        staging = job_dir / "staging" / workspace.dst_path.name
        staging.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.codec.encode_file(acsm.to_bytes(), staging)
            # 再次解码，确认编码产物可解析。
            AcsmDocument(self.codec.decode_file(staging))
        except Exception as exc:  # noqa: BLE001 - 应用边界必须释放工作区写锁
            self.database.update_job(job_id, JobStatus.FAILED, 0, getattr(exc, "code", "DST_ROUNDTRIP_FAILED"))
            return self.database.get_job(job_id) or {}
        self.database.update_job(job_id, JobStatus.PREPARED, 70)
        before_hash = file_sha256(workspace.dst_path)
        self.database.update_job(job_id, JobStatus.PUBLISHING, 90)
        append_operation_event(workspace.root, job_id, "PUBLISHING", file_count=1)
        try:
            revision_dir = self.publisher.publish(operation_id, workspace.root, {workspace.dst_path: staging})
        except PublishRolledBackError:
            self.database.update_job(job_id, JobStatus.ROLLED_BACK, 0, "PUBLISH_ROLLED_BACK")
            return self.database.get_job(job_id) or {}
        except Exception as exc:  # noqa: BLE001 - 应用边界必须释放工作区写锁
            self.database.update_job(job_id, JobStatus.FAILED, 0, getattr(exc, "code", "PUBLISH_FAILED"))
            return self.database.get_job(job_id) or {}
        result_hash = file_sha256(workspace.dst_path)
        self.database.add_revision(result_hash, workspace_id, operation_id, before_hash, result_hash, revision_dir)
        write_workspace_metadata(workspace.root, workspace.id, workspace.dst_path, result_hash, cad_version)
        self.database.update_job(job_id, JobStatus.SUCCEEDED, 100)
        append_operation_event(workspace.root, job_id, "SUCCEEDED", revision_id=result_hash)
        shutil.copytree(workspace.root / ".dst-manager" / "jobs" / job_id / "logs", revision_dir / "logs", dirs_exist_ok=True)
        return self.database.get_job(job_id) or {}

    def run_next_job(self) -> dict[str, Any] | None:
        worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        job = self.database.claim_next_job(worker_id)
        if job is None:
            return None
        workspace = self.get_workspace(job["workspace_id"])
        capability = self._capability(job["cad_version"] or "2020")
        runner = CadJobRunner(
            self.database,
            self.codec,
            self.publisher,
            self.settings.cad_timeout_seconds,
            self.settings.cad_max_parallel,
        )
        return runner.run(job, workspace, capability)

    def retry_job(self, job_id: str) -> dict[str, Any]:
        try:
            return self.database.retry_job(job_id)
        except KeyError as exc:
            raise ApplicationError("JOB_NOT_FOUND", "任务不存在", 404) from exc
        except ValueError as exc:
            raise ApplicationError("JOB_NOT_RETRYABLE", "当前任务状态不允许重试", 409) from exc
        except WorkspaceBusyError as exc:
            raise ApplicationError("WORKSPACE_WRITE_BUSY", str(exc), 409) from exc

    def get_job_details(self, job_id: str) -> dict[str, Any]:
        job = self.database.get_job(job_id)
        if job is None:
            raise ApplicationError("JOB_NOT_FOUND", "任务不存在", 404)
        row = self.database.get_workspace(job["workspace_id"])
        root = Path(row.root) if row else None
        files = []
        for item in job["files"]:
            public = dict(item)
            log_value = public.get("log_path")
            if log_value and Path(log_value).is_file():
                text = Path(log_value).read_text(encoding="utf-8", errors="replace")[-4000:]
                text = re.sub(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+", r"\1=<REDACTED>", text)
                if root:
                    text = text.replace(str(root), "<WORKSPACE>")
                text = text.replace(str(Path.home()), "<USER_HOME>")
                public["log_summary"] = text
            for key in ("target_path", "source_path", "log_path"):
                value = public.get(key)
                if value and root:
                    try:
                        public[key] = str(Path(value).resolve().relative_to(root.resolve()))
                    except ValueError:
                        public[key] = Path(value).name
            files.append(public)
        job["files"] = files
        job["summary"] = {
            "total": len(files),
            "succeeded": sum(item["status"] == "SUCCEEDED" for item in files),
            "failed": sum(item["status"] == "FAILED" for item in files),
            "duration_ms": sum(item.get("duration_ms") or 0 for item in files),
        }
        suggestions = {
            "CAD_CAPABILITY_UNAVAILABLE": "配置匹配版本的 Core Console 和 Worker 插件后重试。",
            "BLOCKED_FILE_LOCK": "关闭占用目标 DST/DWG 的程序后重试。",
            "TEMPLATE_CHANGED": "模板已变化，请重新预览后提交。",
            "CAD_TIMEOUT": "检查 CAD 日志、图纸复杂度和超时设置后重试。",
            "STAGING_DISK_SPACE_INSUFFICIENT": "释放工作区磁盘空间后重试。",
            "HANDLE_LAYOUT_MISMATCH": "检查模板布局名和 Worker 插件版本。",
            "PUBLISH_JOURNAL_REVIEW_REQUIRED": "先核对发布日志并完成恢复，禁止直接重跑。",
        }
        job["suggestion"] = suggestions.get(job["error_code"], "查看逐 DWG 日志和错误详情后决定是否重试。" if job["error_code"] else None)
        return job

    def preview_revision_restore(self, workspace_id: str, revision_id: str) -> dict[str, Any]:
        workspace_row = self.database.get_workspace(workspace_id)
        if workspace_row is None:
            raise ApplicationError("WORKSPACE_NOT_FOUND", "工作区不存在", 404)
        workspace_root = Path(workspace_row.root)
        dst_path = Path(workspace_row.dst_path)
        revision = self.database.get_revision(revision_id)
        if revision is None or revision["workspace_id"] != workspace_id:
            raise ApplicationError("REVISION_NOT_FOUND", "修订不存在", 404)
        manifest_path = Path(revision["revision_dir"]) / "manifest.json"
        if not manifest_path.is_file():
            raise ApplicationError("REVISION_MANIFEST_MISSING", "修订清单缺失", 409)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = []
        conflicts = []
        for entry in manifest["files"]:
            target = Path(entry["target"])
            current_hash = file_sha256(target) if target.exists() else None
            expected_hash = entry.get("result_hash")
            conflict = current_hash != expected_hash
            action = "replace" if entry.get("backup") else "delete"
            item = {"path": str(target.relative_to(workspace_root)), "action": action, "current_hash": current_hash, "expected_hash": expected_hash, "restore_hash": entry.get("before_hash"), "conflict": conflict}
            files.append(item)
            if conflict:
                conflicts.append(item["path"])
        return {"workspace_id": workspace_id, "revision_id": revision_id, "base_revision_id": file_sha256(dst_path), "files": files, "conflicts": conflicts, "executable": not conflicts}

    def restore_revision(self, workspace_id: str, revision_id: str, base_revision_id: str) -> dict[str, Any]:
        preview = self.preview_revision_restore(workspace_id, revision_id)
        if preview["base_revision_id"] != base_revision_id or not preview["executable"]:
            raise ApplicationError("REVISION_RESTORE_CONFLICT", "当前文件已变化，请重新预览恢复", 409)
        workspace = self.get_workspace(workspace_id)
        revision = self.database.get_revision(revision_id)
        manifest = json.loads((Path(revision["revision_dir"]) / "manifest.json").read_text(encoding="utf-8"))
        job_id = str(uuid.uuid4())
        try:
            self.database.create_job(job_id, workspace_id, "revision_restore", JobStatus.STAGING, {"base_revision_id": base_revision_id, "source_revision_id": revision_id})
        except WorkspaceBusyError as exc:
            raise ApplicationError("WORKSPACE_WRITE_BUSY", str(exc), 409) from exc
        staging_dir = workspace.root / ".dst-manager" / "jobs" / job_id / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        staged: dict[Path, Path | None] = {}
        for index, entry in enumerate(manifest["files"]):
            target = Path(entry["target"])
            if entry.get("backup"):
                source = Path(entry["backup"])
                staged_copy = staging_dir / f"{index:03d}-{target.name}"
                shutil.copy2(source, staged_copy)
                staged[target] = staged_copy
            else:
                staged[target] = None
        self.database.update_job(job_id, JobStatus.PREPARED, 70)
        before_hash = file_sha256(workspace.dst_path)
        self.database.update_job(job_id, JobStatus.PUBLISHING, 90)
        try:
            revision_dir = self.publisher.publish(job_id, workspace.root, staged)
        except PublishRolledBackError as exc:
            self.database.update_job(job_id, JobStatus.ROLLED_BACK, 0, exc.code)
            return self.database.get_job(job_id) or {}
        result_hash = file_sha256(workspace.dst_path)
        record_id = f"restore-{job_id}"
        self.database.add_revision(record_id, workspace_id, job_id, before_hash, result_hash, revision_dir, current_revision=result_hash)
        workspace_row = self.database.get_workspace(workspace_id)
        write_workspace_metadata(workspace.root, workspace.id, workspace.dst_path, result_hash, workspace_row.default_cad_version if workspace_row else "2020")
        self.database.update_job(job_id, JobStatus.SUCCEEDED, 100)
        append_operation_event(workspace.root, job_id, "REVISION_RESTORED", source_revision_id=revision_id, revision_id=record_id)
        return self.database.get_job(job_id) or {}

    def preview_xml(self, workspace_id: str, base_revision_id: str, xml: bytes) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        imported = AcsmDocument(xml).project(workspace.root)
        before_sheets = {sheet.acsm_id: sheet for sheet in workspace.document.sheets}
        after_sheets = {sheet.acsm_id: sheet for sheet in imported.sheets}
        changes: list[dict[str, Any]] = []
        for sheet_id in sorted(before_sheets.keys() - after_sheets.keys()):
            changes.append({"type": "sheet_removed", "sheet_id": sheet_id, "before": {"number": before_sheets[sheet_id].number, "title": before_sheets[sheet_id].title}})
        for sheet_id in sorted(after_sheets.keys() - before_sheets.keys()):
            changes.append({"type": "sheet_added", "sheet_id": sheet_id, "after": {"number": after_sheets[sheet_id].number, "title": after_sheets[sheet_id].title}})
        for sheet_id in sorted(before_sheets.keys() & after_sheets.keys()):
            before, after = before_sheets[sheet_id], after_sheets[sheet_id]
            fields = {}
            for name in ("number", "title", "custom_properties"):
                if getattr(before, name) != getattr(after, name):
                    fields[name] = {"before": getattr(before, name), "after": getattr(after, name)}
            if (before.layout.file_name, before.layout.layout_name, before.layout.handle) != (after.layout.file_name, after.layout.layout_name, after.layout.handle):
                fields["layout"] = {"before": asdict(before.layout), "after": asdict(after.layout)}
            if fields:
                changes.append({"type": "sheet_changed", "sheet_id": sheet_id, "fields": fields})
        return {"sheet_count_before": len(workspace.document.sheets), "sheet_count_after": len(imported.sheets), "subset_count_before": len(workspace.document.subsets), "subset_count_after": len(imported.subsets), "changes": changes, "diagnostics": [asdict(issue) for issue in imported.diagnostics]}

    def export_xml_to_dst(self, workspace_id: str, base_revision_id: str, xml: bytes, destination: Path) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        document = AcsmDocument(xml)
        errors = [issue for issue in document.validate() if issue.severity == Severity.ERROR]
        if errors:
            raise ApplicationError("XML_VALIDATION_FAILED", f"XML存在{len(errors)}个阻断问题")
        destination = destination.expanduser().resolve()
        if workspace.root != destination.parent and workspace.root not in destination.parents:
            raise ApplicationError("DESTINATION_OUTSIDE_WORKSPACE", "导出位置必须在工作区内")
        job_id = str(uuid.uuid4())
        try:
            self.database.create_job(job_id, workspace_id, "xml_export", JobStatus.STAGING, {"base_revision_id": base_revision_id, "destination": str(destination)})
        except WorkspaceBusyError as exc:
            raise ApplicationError("WORKSPACE_WRITE_BUSY", str(exc), 409) from exc
        job_dir = workspace.root / ".dst-manager" / "jobs" / job_id
        input_path, staged = job_dir / "input" / "imported.xml", job_dir / "staging" / destination.name
        input_path.parent.mkdir(parents=True, exist_ok=True)
        staged.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_bytes(xml)
        append_operation_event(workspace.root, job_id, "STAGING", job_type="xml_export")
        self.codec.encode_file(document.to_bytes(), staged)
        roundtrip = AcsmDocument(self.codec.decode_file(staged))
        if roundtrip.semantic_bytes() != document.semantic_bytes():
            self.database.update_job(job_id, JobStatus.FAILED, 0, "DST_ROUNDTRIP_MISMATCH")
            return self.database.get_job(job_id) or {}
        self.database.update_job(job_id, JobStatus.PREPARED, 70)
        before_hash = file_sha256(destination) if destination.exists() else base_revision_id
        self.database.update_job(job_id, JobStatus.PUBLISHING, 90)
        append_operation_event(workspace.root, job_id, "PUBLISHING", file_count=1)
        try:
            revision_dir = self.publisher.publish(job_id, workspace.root, {destination: staged})
        except PublishRolledBackError:
            self.database.update_job(job_id, JobStatus.ROLLED_BACK, 0, "PUBLISH_ROLLED_BACK")
            return self.database.get_job(job_id) or {}
        except Exception as exc:  # noqa: BLE001 - 应用边界必须释放工作区写锁
            self.database.update_job(job_id, JobStatus.FAILED, 0, getattr(exc, "code", "PUBLISH_FAILED"))
            return self.database.get_job(job_id) or {}
        result_hash = file_sha256(destination)
        revision_input = revision_dir / "input"
        revision_input.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, revision_input / "imported.xml")
        is_main = destination == workspace.dst_path
        revision_id = result_hash if is_main else f"{base_revision_id[:24]}-{job_id}"
        self.database.add_revision(revision_id, workspace_id, job_id, before_hash, result_hash, revision_dir, update_current=is_main)
        if is_main:
            write_workspace_metadata(workspace.root, workspace.id, workspace.dst_path, result_hash, "2020")
        self.database.update_job(job_id, JobStatus.SUCCEEDED, 100)
        append_operation_event(workspace.root, job_id, "SUCCEEDED", revision_id=revision_id)
        shutil.copytree(job_dir / "logs", revision_dir / "logs", dirs_exist_ok=True)
        return self.database.get_job(job_id) or {}

    def capabilities(self) -> dict[str, dict[str, Any]]:
        capabilities = {version: self._capability(version) for version in ("2016", "2020")}
        return {version: {"version": version, "available": item.available, "console": str(item.console) if item.console else None, "plugin": str(item.plugin) if item.plugin else None} for version, item in capabilities.items()}

    def inspect_template(self, template: Path, cad_version: str) -> dict[str, Any]:
        template = template.expanduser().resolve()
        if template.suffix.lower() not in {".dwg", ".dwt"} or not template.is_file():
            raise ApplicationError("TEMPLATE_NOT_FOUND", f"模板不存在：{template}", 404)
        capability = self._capability(cad_version)
        if not capability.available:
            raise ApplicationError("CAD_CAPABILITY_UNAVAILABLE", f"AutoCAD {cad_version}未配置")
        source_hash = file_sha256(template)
        with tempfile.TemporaryDirectory(prefix="dst-manager-template-") as temp:
            temp_dir = Path(temp)
            drawing = temp_dir / (template.stem + ".dwg")
            import shutil
            shutil.copy2(template, drawing)
            script = temp_dir / "inspect.scr"
            script.write_text(ScriptRenderer().render_handles(capability.plugin), encoding="mbcs")
            CoreConsoleExecutor().run(capability, drawing, script, self.settings.cad_timeout_seconds)
            handles = parse_handles(drawing.with_suffix(".dst-handles.txt").read_text(encoding="utf-8"))
        if file_sha256(template) != source_hash:
            raise ApplicationError("TEMPLATE_CHANGED", "模板在检查期间发生变化")
        return {"path": str(template), "sha256": source_hash, "cad_version": cad_version, "layouts": [{"name": name, "handle": handle} for name, handle in handles.items()]}

    def _capability(self, version: str) -> CadCapability:
        if version == "2016":
            return CadCapability(version, self.settings.autocad_2016_console, self.settings.autocad_2016_plugin)
        if version == "2020":
            return CadCapability(version, self.settings.autocad_2020_console, self.settings.autocad_2020_plugin)
        raise ApplicationError("CAD_VERSION_INVALID", f"不支持的AutoCAD版本：{version}")

    def _check_revision(self, workspace: Workspace, base_revision_id: str) -> None:
        if workspace.revision_id != base_revision_id:
            raise ApplicationError("REVISION_CONFLICT", "基准修订已变化，请重新预览", 409)

    @staticmethod
    def _issue(code: str, severity: str, message: str):
        from dst_manager.domain.models import ValidationIssue
        return ValidationIssue(code, Severity(severity), message)

    @staticmethod
    def _write_workspace_file(workspace: Workspace) -> None:
        write_workspace_metadata(workspace.root, workspace.id, workspace.dst_path, workspace.revision_id, "2020")
