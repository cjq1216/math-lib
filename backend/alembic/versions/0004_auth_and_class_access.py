"""add auth sessions and class teachers

Revision ID: 0004_auth_and_class_access
Revises: 0003_background_tasks
Create Date: 2026-09-13
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_auth_and_class_access"
down_revision = "0003_background_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_jti", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("refresh_jti", name="uq_auth_sessions_refresh_jti"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_refresh_jti", "auth_sessions", ["refresh_jti"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_index("ix_auth_sessions_revoked_at", "auth_sessions", ["revoked_at"])
    op.create_index("ix_auth_sessions_created_at", "auth_sessions", ["created_at"])

    op.create_table(
        "class_teachers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("class_id", sa.Integer, sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("teacher_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("class_id", "teacher_id", name="uq_class_teachers_class_teacher"),
    )
    op.create_index("ix_class_teachers_class_id", "class_teachers", ["class_id"])
    op.create_index("ix_class_teachers_teacher_id", "class_teachers", ["teacher_id"])

    classes = sa.table(
        "classes",
        sa.column("id", sa.Integer),
        sa.column("head_teacher_id", sa.Integer),
        sa.column("created_by", sa.Integer),
    )
    class_teachers = sa.table(
        "class_teachers",
        sa.column("class_id", sa.Integer),
        sa.column("teacher_id", sa.Integer),
        sa.column("assigned_by", sa.Integer),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(classes.c.id, classes.c.head_teacher_id, classes.c.created_by).where(
            classes.c.head_teacher_id.is_not(None)
        )
    )
    assignments = [
        {
            "class_id": row.id,
            "teacher_id": row.head_teacher_id,
            "assigned_by": row.created_by,
        }
        for row in rows
    ]
    if assignments:
        connection.execute(class_teachers.insert(), assignments)


def downgrade() -> None:
    op.drop_index("ix_class_teachers_teacher_id", table_name="class_teachers")
    op.drop_index("ix_class_teachers_class_id", table_name="class_teachers")
    op.drop_table("class_teachers")

    op.drop_index("ix_auth_sessions_created_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_revoked_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_refresh_jti", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
