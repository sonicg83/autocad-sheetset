import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dst_manager.infrastructure.persistence.database import (
    Database,
    InvalidJobTransitionError,
    WorkspaceBusyError,
)


def test_published_migrations_are_immutable():
    expected = {
        "0001_initial.py": "d19d09f9984eaa7bfe93932fb9971583f5c08bc28bed0c26a79b8f54af9df4f1",
        "0002_v02_job_reliability.py": "f318c1c9c0de34f23d6d41fe3677ebb38a51f2d528a3449ada4f6ff81f7a122c",
    }
    migration_root = Path("migrations/versions")
    actual = {
        name: hashlib.sha256((migration_root / name).read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest()
        for name in expected
    }
    assert actual == expected, "已发布 migration 不可原地修改；schema 变化必须新增 revision"


def test_workspace_allows_only_one_active_write_job(tmp_path: Path):
    database=Database(f"sqlite:///{(tmp_path/'db.sqlite').as_posix()}"); root=tmp_path/"project"; root.mkdir(); dst=root/"a.dst"; dst.write_bytes(b"x"); database.upsert_workspace("w",root,dst,"rev")
    database.create_job("job-1","w","change_set","QUEUED",{})
    with pytest.raises(WorkspaceBusyError): database.create_job("job-2","w","change_set","QUEUED",{})
    database.update_job("job-1","FAILED",0,"TEST")
    database.create_job("job-2","w","change_set","QUEUED",{})


def test_illegal_job_status_transition_is_rejected(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    database.create_job("job", "w", "change_set", "QUEUED", {})
    with pytest.raises(InvalidJobTransitionError):
        database.update_job("job", "SUCCEEDED", 100)


def test_claim_is_atomic_and_records_lease(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    database.create_job("job-1", "w", "change_set", "QUEUED", {})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(database.claim_next_job, ("worker-a", "worker-b")))
    claimed = [item for item in results if item]
    assert len(claimed) == 1
    assert claimed[0]["attempt"] == 1
    assert claimed[0]["worker_id"] in {"worker-a", "worker-b"}
    assert claimed[0]["heartbeat_at"]


def test_stale_safe_stage_requeues_and_publish_requires_review(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    old = datetime.now(UTC) - timedelta(minutes=10)
    for index, status in enumerate(("CAD_RUNNING", "PUBLISHING"), 1):
        workspace = f"w-{index}"
        database.upsert_workspace(workspace, tmp_path, tmp_path / f"{index}.dst", "r")
        database.create_job(f"job-{index}", workspace, "change_set", status, {})
        with database.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE jobs SET heartbeat_at=? WHERE id=?", (old.replace(tzinfo=None), f"job-{index}"))
    conclusions = {item["id"]: item["conclusion"] for item in database.recover_stale_jobs(30)}
    assert conclusions == {"job-1": "REQUEUED_SAFE_STAGE", "job-2": "PUBLISH_JOURNAL_REVIEW_REQUIRED"}
    assert database.get_job("job-1")["status"] == "QUEUED"
    assert database.get_job("job-2")["status"] == "NEEDS_REVIEW"
    with pytest.raises(ValueError, match="JOB_NOT_RETRYABLE"):
        database.retry_job("job-2")


def test_existing_mvp_database_is_upgraded_by_alembic(tmp_path: Path):
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
        CREATE TABLE workspaces (id VARCHAR(36) PRIMARY KEY, root TEXT NOT NULL, dst_path TEXT NOT NULL, root_override TEXT, current_revision VARCHAR(64) NOT NULL, default_cad_version VARCHAR(4) NOT NULL, version INTEGER NOT NULL);
        CREATE TABLE document_revisions (id VARCHAR(64) PRIMARY KEY, workspace_id VARCHAR(36) NOT NULL, operation_id VARCHAR(36) NOT NULL, before_hash VARCHAR(64) NOT NULL, result_hash VARCHAR(64) NOT NULL, revision_dir TEXT NOT NULL, created_at DATETIME NOT NULL);
        CREATE TABLE change_sets (id VARCHAR(36) PRIMARY KEY, workspace_id VARCHAR(36) NOT NULL, base_revision VARCHAR(64) NOT NULL, commands_json TEXT NOT NULL, status VARCHAR(32) NOT NULL, validation_summary TEXT NOT NULL);
        CREATE TABLE jobs (id VARCHAR(36) PRIMARY KEY, workspace_id VARCHAR(36) NOT NULL, job_type VARCHAR(40) NOT NULL, cad_version VARCHAR(4), status VARCHAR(32) NOT NULL, progress INTEGER NOT NULL, payload_json TEXT NOT NULL, error_code VARCHAR(80), created_at DATETIME NOT NULL);
        CREATE TABLE job_files (id INTEGER PRIMARY KEY, job_id VARCHAR(36) NOT NULL, source_path TEXT, target_path TEXT NOT NULL, before_hash VARCHAR(64), result_hash VARCHAR(64), role VARCHAR(32) NOT NULL, result VARCHAR(32));
        CREATE TABLE diagnostics (id INTEGER PRIMARY KEY, job_id VARCHAR(36), workspace_id VARCHAR(36) NOT NULL, severity VARCHAR(16) NOT NULL, code VARCHAR(80) NOT NULL, object_id VARCHAR(64), location TEXT, message TEXT NOT NULL);
        CREATE TABLE templates (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, sha256 VARCHAR(64) NOT NULL, layouts_json TEXT NOT NULL, cad_version VARCHAR(4) NOT NULL);
        CREATE TABLE application_settings (key VARCHAR(100) PRIMARY KEY, value_json TEXT NOT NULL);
        CREATE TABLE workspace_write_locks (workspace_id VARCHAR(36) PRIMARY KEY, job_id VARCHAR(36) UNIQUE NOT NULL);
        """)
    database = Database(f"sqlite:///{path.as_posix()}")
    with database.engine.connect() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(jobs)")}
        revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    assert {"worker_id", "attempt", "heartbeat_at", "finished_at"} <= columns
    assert revision == "0002_v02_job_reliability"


def test_outdated_schema_is_rejected_when_migration_is_disabled(tmp_path: Path):
    path = tmp_path / "db.sqlite"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE alembic_version SET version_num='0001_initial'")
    with pytest.raises(RuntimeError, match="DATABASE_SCHEMA_INCOMPATIBLE.*alembic upgrade head"):
        Database(f"sqlite:///{path.as_posix()}", migrate=False)


@pytest.mark.parametrize(
    ("damage_sql", "missing"),
    [
        ("DROP TABLE job_events", "缺少表=job_events"),
        ("ALTER TABLE jobs DROP COLUMN error_detail", "缺少列=jobs.error_detail"),
    ],
)
def test_latest_revision_with_physical_schema_drift_is_rejected(tmp_path: Path, damage_sql: str, missing: str):
    path = tmp_path / "drift.sqlite"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute(damage_sql)

    with pytest.raises(RuntimeError, match=f"DATABASE_SCHEMA_DRIFT.*{missing}"):
        Database(f"sqlite:///{path.as_posix()}", migrate=False)
