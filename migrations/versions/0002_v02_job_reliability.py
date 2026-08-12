"""补充 v0.2 任务租约、错误详情和逐 DWG 执行状态。"""

import sqlalchemy as sa
from alembic import op

revision = "0002_v02_job_reliability"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("worker_id", sa.String(100), nullable=True))
        batch.add_column(sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("error_detail", sa.Text(), nullable=True))
    with op.batch_alter_table("job_files") as batch:
        batch.add_column(sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"))
        batch.add_column(sa.Column("progress", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("peak_memory_bytes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("staging_bytes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("log_path", sa.Text(), nullable=True))
        batch.add_column(sa.Column("error_code", sa.String(80), nullable=True))
        batch.add_column(sa.Column("error_detail", sa.Text(), nullable=True))
    op.create_table(
        "job_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("job_events")
    with op.batch_alter_table("job_files") as batch:
        for name in ("error_detail", "error_code", "log_path", "staging_bytes", "peak_memory_bytes", "duration_ms", "progress", "status"):
            batch.drop_column(name)
    with op.batch_alter_table("jobs") as batch:
        for name in ("error_detail", "finished_at", "heartbeat_at", "started_at", "attempt", "worker_id"):
            batch.drop_column(name)
