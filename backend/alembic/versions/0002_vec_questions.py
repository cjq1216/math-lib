"""add portable question embedding storage

Revision ID: 0002_vec_questions
Revises: 0001_initial
Create Date: 2026-09-12

基础迁移只保存向量数据，不要求 SQLite 安装 sqlite-vec。相似度索引在后续
迭代按运行数据库单独启用，避免可选扩展阻断空库启动。
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_vec_questions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_embeddings",
        sa.Column(
            "question_id",
            sa.Integer,
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("embedding", sa.JSON, nullable=False),
        sa.Column("dimensions", sa.Integer, nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("question_embeddings")
