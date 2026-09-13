"""add background_tasks table

Revision ID: 0003_background_tasks
Revises: 0002_vec_questions
Create Date: 2026-09-12

用于异步任务状态追踪（切题/打标/Embedding）。
"""
import sqlalchemy as sa

from alembic import op

revision = "0003_background_tasks"
down_revision = "0002_vec_questions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_type", sa.String(32), index=True, nullable=False),
        sa.Column("status", sa.String(16), index=True, nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("progress_message", sa.String(512), nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("error_traceback", sa.Text, nullable=True),
        sa.Column("resource_type", sa.String(32), nullable=True),
        sa.Column("resource_id", sa.Integer, index=True, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("estimated_duration_seconds", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("background_tasks")
