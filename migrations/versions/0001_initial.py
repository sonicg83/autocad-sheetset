"""DST Manager MVP初始数据模型。"""
import sqlalchemy as sa
from alembic import op

revision="0001_initial"; down_revision=None; branch_labels=None; depends_on=None

def upgrade():
    op.create_table("workspaces",sa.Column("id",sa.String(36),primary_key=True),sa.Column("root",sa.Text(),nullable=False),sa.Column("dst_path",sa.Text(),nullable=False),sa.Column("root_override",sa.Text()),sa.Column("current_revision",sa.String(64),nullable=False),sa.Column("default_cad_version",sa.String(4),nullable=False),sa.Column("version",sa.Integer(),nullable=False))
    op.create_table("document_revisions",sa.Column("id",sa.String(64),primary_key=True),sa.Column("workspace_id",sa.String(36),sa.ForeignKey("workspaces.id"),nullable=False),sa.Column("operation_id",sa.String(36),nullable=False),sa.Column("before_hash",sa.String(64),nullable=False),sa.Column("result_hash",sa.String(64),nullable=False),sa.Column("revision_dir",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("change_sets",sa.Column("id",sa.String(36),primary_key=True),sa.Column("workspace_id",sa.String(36),sa.ForeignKey("workspaces.id"),nullable=False),sa.Column("base_revision",sa.String(64),nullable=False),sa.Column("commands_json",sa.Text(),nullable=False),sa.Column("status",sa.String(32),nullable=False),sa.Column("validation_summary",sa.Text(),nullable=False))
    op.create_table("jobs",sa.Column("id",sa.String(36),primary_key=True),sa.Column("workspace_id",sa.String(36),sa.ForeignKey("workspaces.id"),nullable=False),sa.Column("job_type",sa.String(40),nullable=False),sa.Column("cad_version",sa.String(4)),sa.Column("status",sa.String(32),nullable=False),sa.Column("progress",sa.Integer(),nullable=False),sa.Column("payload_json",sa.Text(),nullable=False),sa.Column("error_code",sa.String(80)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("job_files",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("job_id",sa.String(36),sa.ForeignKey("jobs.id"),nullable=False),sa.Column("source_path",sa.Text()),sa.Column("target_path",sa.Text(),nullable=False),sa.Column("before_hash",sa.String(64)),sa.Column("result_hash",sa.String(64)),sa.Column("role",sa.String(32),nullable=False),sa.Column("result",sa.String(32)))
    op.create_table("diagnostics",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("job_id",sa.String(36),sa.ForeignKey("jobs.id")),sa.Column("workspace_id",sa.String(36),sa.ForeignKey("workspaces.id"),nullable=False),sa.Column("severity",sa.String(16),nullable=False),sa.Column("code",sa.String(80),nullable=False),sa.Column("object_id",sa.String(64)),sa.Column("location",sa.Text()),sa.Column("message",sa.Text(),nullable=False))
    op.create_table("templates",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("path",sa.Text(),unique=True,nullable=False),sa.Column("sha256",sa.String(64),nullable=False),sa.Column("layouts_json",sa.Text(),nullable=False),sa.Column("cad_version",sa.String(4),nullable=False))
    op.create_table("application_settings",sa.Column("key",sa.String(100),primary_key=True),sa.Column("value_json",sa.Text(),nullable=False))
    op.create_table("workspace_write_locks",sa.Column("workspace_id",sa.String(36),sa.ForeignKey("workspaces.id"),primary_key=True),sa.Column("job_id",sa.String(36),unique=True,nullable=False))

def downgrade():
    for table in ("workspace_write_locks","application_settings","templates","diagnostics","job_files","jobs","change_sets","document_revisions","workspaces"): op.drop_table(table)
