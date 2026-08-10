import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    select,
    text,
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


class Database:
    def __init__(self, url: str):
        self.engine = create_engine(url)

        @event.listens_for(self.engine, "connect")
        def _configure(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(workspaces)"))}
            if "root_override" not in columns:
                connection.execute(text("ALTER TABLE workspaces ADD COLUMN root_override TEXT"))
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

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
            session.add(WorkspaceWriteLockRow(workspace_id=workspace_id, job_id=job_id))

    def update_job(self, job_id: str, status: str, progress: int, error_code: str | None = None) -> None:
        with self.sessions.begin() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                raise KeyError(job_id)
            row.status, row.progress, row.error_code = status, progress, error_code
            if status in {"SUCCEEDED", "FAILED", "BLOCKED_FILE_LOCK", "ROLLED_BACK"}:
                lock = session.get(WorkspaceWriteLockRow, row.workspace_id)
                if lock and lock.job_id == job_id:
                    session.delete(lock)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.sessions() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                return None
            return {"id": row.id, "workspace_id": row.workspace_id, "type": row.job_type, "status": row.status, "progress": row.progress, "cad_version": row.cad_version, "error_code": row.error_code, "payload": json.loads(row.payload_json)}

    def claim_next_job(self) -> dict[str, Any] | None:
        """单Worker原子领取一个排队任务。"""
        with self.sessions.begin() as session:
            row = session.scalars(select(JobRow).where(JobRow.status == "QUEUED").order_by(JobRow.created_at).limit(1)).first()
            if row is None:
                return None
            row.status, row.progress = "STAGING", 5
            session.flush()
            return {"id": row.id, "workspace_id": row.workspace_id, "type": row.job_type, "status": row.status, "progress": row.progress, "cad_version": row.cad_version, "error_code": row.error_code, "payload": json.loads(row.payload_json)}

    def add_revision(self, revision_id: str, workspace_id: str, operation_id: str, before_hash: str, result_hash: str, revision_dir: Path, update_current: bool = True) -> None:
        with self.sessions.begin() as session:
            session.add(RevisionRow(id=revision_id, workspace_id=workspace_id, operation_id=operation_id, before_hash=before_hash, result_hash=result_hash, revision_dir=str(revision_dir)))
            workspace = session.get(WorkspaceRow, workspace_id)
            if workspace and update_current:
                workspace.current_revision = revision_id

    def list_revisions(self) -> list[dict[str, Any]]:
        with self.sessions() as session:
            rows = session.scalars(select(RevisionRow).order_by(RevisionRow.created_at.desc())).all()
            return [{"id": row.id, "workspace_id": row.workspace_id, "operation_id": row.operation_id, "before_hash": row.before_hash, "result_hash": row.result_hash, "revision_dir": row.revision_dir, "created_at": row.created_at.isoformat()} for row in rows]

    def list_workspace_roots(self) -> list[Path]:
        with self.sessions() as session:
            return [Path(value) for value in session.scalars(select(WorkspaceRow.root)).all()]
