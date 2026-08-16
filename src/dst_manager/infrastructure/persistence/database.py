import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)


class Base(DeclarativeBase):
    pass


class WorkspaceRow(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    root: Mapped[str] = mapped_column(Text)
    dst_path: Mapped[str] = mapped_column(Text)
    root_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_revision: Mapped[str] = mapped_column(String(64))
    default_cad_version: Mapped[str] = mapped_column(String(4), default="2020")
    version: Mapped[int] = mapped_column(Integer, default=1)
    jobs: Mapped[list["JobRow"]] = relationship(back_populates="workspace")


class RevisionRow(Base):
    __tablename__ = "document_revisions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    operation_id: Mapped[str] = mapped_column(String(36))
    before_hash: Mapped[str] = mapped_column(String(64))
    result_hash: Mapped[str] = mapped_column(String(64))
    revision_dir: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ChangeSetRow(Base):
    __tablename__ = "change_sets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    base_revision: Mapped[str] = mapped_column(String(64))
    commands_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    validation_summary: Mapped[str] = mapped_column(Text, default="{}")


class JobRow(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    job_type: Mapped[str] = mapped_column(String(40))
    cad_version: Mapped[str | None] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(32))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_detail: Mapped[str | None] = mapped_column(Text)
    worker_id: Mapped[str | None] = mapped_column(String(100))
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    workspace: Mapped[WorkspaceRow] = relationship(back_populates="jobs")


class JobFileRow(Base):
    __tablename__ = "job_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    source_path: Mapped[str | None] = mapped_column(Text)
    target_path: Mapped[str] = mapped_column(Text)
    before_hash: Mapped[str | None] = mapped_column(String(64))
    result_hash: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))
    result: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    peak_memory_bytes: Mapped[int | None] = mapped_column(Integer)
    staging_bytes: Mapped[int | None] = mapped_column(Integer)
    log_path: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_detail: Mapped[str | None] = mapped_column(Text)


class JobEventRow(Base):
    __tablename__ = "job_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    status: Mapped[str] = mapped_column(String(32))
    progress: Mapped[int] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class DiagnosticRow(Base):
    __tablename__ = "diagnostics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    severity: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)


class TemplateRow(Base):
    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    layouts_json: Mapped[str] = mapped_column(Text)
    cad_version: Mapped[str] = mapped_column(String(4))


class ApplicationSettingRow(Base):
    __tablename__ = "application_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)


class WorkspaceWriteLockRow(Base):
    __tablename__ = "workspace_write_locks"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True)


class WorkspaceBusyError(RuntimeError):
    pass


class InvalidJobTransitionError(RuntimeError):
    pass


LATEST_SCHEMA_REVISION = "0002_v02_job_reliability"
TERMINAL_JOB_STATUSES = {"SUCCEEDED", "FAILED", "BLOCKED_FILE_LOCK", "ROLLED_BACK", "NEEDS_REVIEW"}
ALLOWED_JOB_TRANSITIONS = {
    "DRAFT": {"VALIDATED", "FAILED"},
    "VALIDATED": {"QUEUED", "STAGING", "FAILED"},
    "QUEUED": {"STAGING", "FAILED"},
    "STAGING": {"CAD_RUNNING", "PREPARED", "FAILED", "BLOCKED_FILE_LOCK"},
    "CAD_RUNNING": {"VERIFYING", "FAILED", "BLOCKED_FILE_LOCK"},
    "VERIFYING": {"PREPARED", "FAILED"},
    "PREPARED": {"PUBLISHING", "FAILED"},
    "PUBLISHING": {"SUCCEEDED", "ROLLING_BACK", "ROLLED_BACK", "FAILED"},
    "ROLLING_BACK": {"ROLLED_BACK", "FAILED"},
}


def migrate_database(url: str) -> None:
    """只通过 Alembic 把空库或既有 MVP 数据库升级到最新版本。"""
    root = Path(__file__).resolve().parents[4]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    if tables and "alembic_version" not in tables:
        # v0.1 曾由 SQLAlchemy create_all 创建同构表；先登记其版本，再由 Alembic 升级。
        mvp_tables = {"workspaces", "document_revisions", "change_sets", "jobs", "job_files", "diagnostics", "templates", "application_settings", "workspace_write_locks"}
        if tables != mvp_tables:
            raise RuntimeError("DATABASE_SCHEMA_UNKNOWN: 数据库不是可识别的 MVP schema，禁止自动迁移")
        command.stamp(config, "0001_initial")
    command.upgrade(config, "head")


class Database:
    def __init__(self, url: str, *, migrate: bool = True):
        if migrate:
            migrate_database(url)
        self.engine = create_engine(url)

        @event.listens_for(self.engine, "connect")
        def _configure(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        self.check_schema()

    def check_schema(self) -> None:
        try:
            with self.engine.connect() as connection:
                revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        except Exception as exc:
            raise RuntimeError("DATABASE_MIGRATION_REQUIRED: 请运行 uv run alembic upgrade head") from exc
        if revision != LATEST_SCHEMA_REVISION:
            raise RuntimeError(
                f"DATABASE_SCHEMA_INCOMPATIBLE: 当前={revision}，需要={LATEST_SCHEMA_REVISION}；"
                "请运行 uv run alembic upgrade head"
            )
        schema = inspect(self.engine)
        physical_tables = set(schema.get_table_names())
        expected_tables = set(Base.metadata.tables)
        missing_tables = sorted(expected_tables - physical_tables)
        missing_columns: list[str] = []
        for table_name in sorted(expected_tables & physical_tables):
            expected_columns = {column.name for column in Base.metadata.tables[table_name].columns}
            physical_columns = {column["name"] for column in schema.get_columns(table_name)}
            missing_columns.extend(f"{table_name}.{name}" for name in sorted(expected_columns - physical_columns))
        if missing_tables or missing_columns:
            details = []
            if missing_tables:
                details.append(f"缺少表={','.join(missing_tables)}")
            if missing_columns:
                details.append(f"缺少列={','.join(missing_columns)}")
            raise RuntimeError(
                "DATABASE_SCHEMA_DRIFT: Alembic revision 与物理 schema 不一致（"
                + "；".join(details)
                + "）；测试数据库请删除后运行 uv run alembic upgrade head 重建"
            )

    def upsert_workspace(self, workspace_id: str, root: Path, dst_path: Path, revision: str, root_override: Path | None = None) -> None:
        with self.sessions.begin() as session:
            row = session.get(WorkspaceRow, workspace_id)
            if row is None:
                session.add(WorkspaceRow(id=workspace_id, root=str(root), dst_path=str(dst_path), current_revision=revision, root_override=str(root_override.resolve()) if root_override else None))
            else:
                row.root, row.dst_path, row.current_revision, row.root_override = str(root), str(dst_path), revision, str(root_override.resolve()) if root_override else row.root_override

    def get_workspace(self, workspace_id: str) -> WorkspaceRow | None:
        with self.sessions() as session:
            return session.get(WorkspaceRow, workspace_id)

    def create_job(self, job_id: str, workspace_id: str, job_type: str, status: str, payload: dict[str, Any], cad_version: str | None = None) -> None:
        with self.sessions.begin() as session:
            lock = session.get(WorkspaceWriteLockRow, workspace_id)
            if lock is not None:
                raise WorkspaceBusyError(f"工作区已有写任务：{lock.job_id}")
            session.add(JobRow(id=job_id, workspace_id=workspace_id, job_type=job_type, status=status, payload_json=json.dumps(payload, ensure_ascii=False), cad_version=cad_version))
            session.flush()
            session.add(JobEventRow(job_id=job_id, status=status, progress=0))
            session.add(WorkspaceWriteLockRow(workspace_id=workspace_id, job_id=job_id))

    def update_job(self, job_id: str, status: str, progress: int, error_code: str | None = None, error_detail: str | None = None) -> None:
        with self.sessions.begin() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                raise KeyError(job_id)
            if status != row.status and status not in ALLOWED_JOB_TRANSITIONS.get(row.status, set()):
                raise InvalidJobTransitionError(f"JOB_STATUS_TRANSITION_INVALID: {row.status}->{status}")
            row.status, row.progress, row.error_code, row.error_detail = status, progress, error_code, error_detail
            session.add(JobEventRow(job_id=job_id, status=status, progress=progress, detail=error_code))
            row.heartbeat_at = datetime.now(UTC)
            if status in TERMINAL_JOB_STATUSES:
                row.finished_at = datetime.now(UTC)
                lock = session.get(WorkspaceWriteLockRow, row.workspace_id)
                if lock and lock.job_id == job_id:
                    session.delete(lock)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.sessions() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                return None
            return self._job_json(session, row)

    def claim_next_job(self, worker_id: str = "local-worker") -> dict[str, Any] | None:
        """单Worker原子领取一个排队任务。"""
        with self.sessions.begin() as session:
            while True:
                job_id = session.scalar(select(JobRow.id).where(JobRow.status == "QUEUED").order_by(JobRow.created_at).limit(1))
                if job_id is None:
                    return None
                now = datetime.now(UTC)
                claimed = session.execute(
                    update(JobRow)
                    .where(JobRow.id == job_id, JobRow.status == "QUEUED")
                    .values(status="STAGING", progress=5, worker_id=worker_id, attempt=JobRow.attempt + 1, started_at=now, heartbeat_at=now, finished_at=None, error_code=None, error_detail=None)
                )
                if claimed.rowcount == 1:
                    session.add(JobEventRow(job_id=job_id, status="STAGING", progress=5, detail=f"worker={worker_id}"))
                    session.flush()
                    return self._job_json(session, session.get(JobRow, job_id))

    def heartbeat(self, job_id: str, worker_id: str) -> bool:
        with self.sessions.begin() as session:
            result = session.execute(update(JobRow).where(JobRow.id == job_id, JobRow.worker_id == worker_id, JobRow.status.not_in(TERMINAL_JOB_STATUSES)).values(heartbeat_at=datetime.now(UTC)))
            return result.rowcount == 1

    def recover_stale_jobs(self, lease_seconds: int = 120) -> list[dict[str, str]]:
        """保守恢复遗留任务；发布阶段一律交给发布日志恢复后再落终态。"""
        cutoff = datetime.now(UTC) - timedelta(seconds=lease_seconds)
        conclusions: list[dict[str, str]] = []
        with self.sessions.begin() as session:
            rows = session.scalars(select(JobRow).where(JobRow.status.not_in(TERMINAL_JOB_STATUSES), JobRow.status != "QUEUED")).all()
            for row in rows:
                heartbeat = row.heartbeat_at
                if heartbeat is not None and heartbeat.tzinfo is None:
                    heartbeat = heartbeat.replace(tzinfo=UTC)
                if heartbeat is not None and heartbeat >= cutoff:
                    continue
                if row.status in {"STAGING", "CAD_RUNNING", "VERIFYING", "PREPARED"}:
                    row.status, conclusion = "QUEUED", "REQUEUED_SAFE_STAGE"
                    row.worker_id = None
                elif row.status in {"PUBLISHING", "ROLLING_BACK"}:
                    row.status, conclusion = "NEEDS_REVIEW", "PUBLISH_JOURNAL_REVIEW_REQUIRED"
                    row.finished_at = datetime.now(UTC)
                else:
                    row.status, conclusion = "NEEDS_REVIEW", "STATE_REVIEW_REQUIRED"
                    row.finished_at = datetime.now(UTC)
                row.error_code = conclusion
                session.add(JobEventRow(job_id=row.id, status=row.status, progress=row.progress, detail=conclusion))
                conclusions.append({"id": row.id, "conclusion": conclusion})
        return conclusions

    def retry_job(self, job_id: str) -> dict[str, Any]:
        with self.sessions.begin() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                raise KeyError(job_id)
            if row.status not in {"FAILED", "BLOCKED_FILE_LOCK", "ROLLED_BACK"}:
                raise ValueError("JOB_NOT_RETRYABLE")
            lock = session.get(WorkspaceWriteLockRow, row.workspace_id)
            if lock is not None and lock.job_id != job_id:
                raise WorkspaceBusyError(f"工作区已有写任务：{lock.job_id}")
            if lock is None:
                session.add(WorkspaceWriteLockRow(workspace_id=row.workspace_id, job_id=row.id))
            row.status, row.progress, row.worker_id = "QUEUED", 0, None
            row.started_at = row.heartbeat_at = row.finished_at = None
            row.error_code = row.error_detail = None
            session.add(JobEventRow(job_id=row.id, status="QUEUED", progress=0, detail="SAFE_RETRY"))
            session.flush()
            return self._job_json(session, row)

    def upsert_job_file(self, job_id: str, target_path: Path, **values: Any) -> None:
        with self.sessions.begin() as session:
            row = session.scalars(select(JobFileRow).where(JobFileRow.job_id == job_id, JobFileRow.target_path == str(target_path))).first()
            if row is None:
                row = JobFileRow(job_id=job_id, target_path=str(target_path), role=values.pop("role", "DWG"))
                session.add(row)
            for key, value in values.items():
                setattr(row, key, value)

    @staticmethod
    def _job_json(session, row: JobRow) -> dict[str, Any]:
        files = session.scalars(select(JobFileRow).where(JobFileRow.job_id == row.id).order_by(JobFileRow.id)).all()
        events = session.scalars(select(JobEventRow).where(JobEventRow.job_id == row.id).order_by(JobEventRow.id)).all()
        return {
            "id": row.id, "workspace_id": row.workspace_id, "type": row.job_type,
            "status": row.status, "progress": row.progress, "cad_version": row.cad_version,
            "error_code": row.error_code, "error_detail": row.error_detail,
            "worker_id": row.worker_id, "attempt": row.attempt,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "heartbeat_at": row.heartbeat_at.isoformat() if row.heartbeat_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "payload": json.loads(row.payload_json),
            "timeline": [{"status": item.status, "progress": item.progress, "detail": item.detail, "at": item.created_at.isoformat()} for item in events],
            "files": [{"target_path": item.target_path, "source_path": item.source_path, "status": item.status, "progress": item.progress, "duration_ms": item.duration_ms, "peak_memory_bytes": item.peak_memory_bytes, "staging_bytes": item.staging_bytes, "log_path": item.log_path, "error_code": item.error_code, "error_detail": item.error_detail, "before_hash": item.before_hash, "result_hash": item.result_hash, "role": item.role} for item in files],
        }

    def add_revision(self, revision_id: str, workspace_id: str, operation_id: str, before_hash: str, result_hash: str, revision_dir: Path, update_current: bool = True, current_revision: str | None = None) -> None:
        with self.sessions.begin() as session:
            session.add(RevisionRow(id=revision_id, workspace_id=workspace_id, operation_id=operation_id, before_hash=before_hash, result_hash=result_hash, revision_dir=str(revision_dir)))
            workspace = session.get(WorkspaceRow, workspace_id)
            if workspace and update_current:
                workspace.current_revision = current_revision or revision_id

    def list_revisions(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        with self.sessions() as session:
            query = select(RevisionRow)
            if workspace_id:
                query = query.where(RevisionRow.workspace_id == workspace_id)
            rows = session.scalars(query.order_by(RevisionRow.created_at.desc())).all()
            return [self._revision_json(row) for row in rows]

    def get_revision(self, revision_id: str) -> dict[str, Any] | None:
        with self.sessions() as session:
            row = session.get(RevisionRow, revision_id)
            return self._revision_json(row) if row else None

    @staticmethod
    def _revision_json(row: RevisionRow) -> dict[str, Any]:
        return {"id": row.id, "workspace_id": row.workspace_id, "operation_id": row.operation_id, "before_hash": row.before_hash, "result_hash": row.result_hash, "revision_dir": row.revision_dir, "created_at": row.created_at.isoformat()}

    def list_workspace_roots(self) -> list[Path]:
        with self.sessions() as session:
            return [Path(value) for value in session.scalars(select(WorkspaceRow.root)).all()]
