"""add question knowledge unique constraint and media integrity

Revision ID: 0006_question_knowledge_unique_and_media_integrity
Revises: 0005_homework_roster_and_question_results
Create Date: 2026-10-02
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_question_knowledge_unique_and_media_integrity"
down_revision = "0005_homework_roster_and_question_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # 1. 清理可能存在的历史重复 question_knowledge 记录（保留 id 最小的一条）
    qk_table = sa.table(
        "question_knowledge",
        sa.column("id", sa.Integer),
        sa.column("question_id", sa.Integer),
        sa.column("knowledge_point_id", sa.Integer),
    )

    rows = connection.execute(
        sa.select(
            qk_table.c.id,
            qk_table.c.question_id,
            qk_table.c.knowledge_point_id,
        ).order_by(qk_table.c.id)
    ).all()

    seen_pairs = set()
    duplicate_ids = []
    for row_id, q_id, kp_id in rows:
        pair = (q_id, kp_id)
        if pair in seen_pairs:
            duplicate_ids.append(row_id)
        else:
            seen_pairs.add(pair)

    if duplicate_ids:
        for dup_id in duplicate_ids:
            connection.execute(
                qk_table.delete().where(qk_table.c.id == dup_id)
            )

    # 2. 为 question_knowledge 创建组合唯一索引
    op.create_index(
        "uq_question_knowledge_question_kp",
        "question_knowledge",
        ["question_id", "knowledge_point_id"],
        unique=True,
    )

    # 3. 校准已存在媒体资源的 reference_count，使其真实等于在 question_media 中的关联数
    media_table = sa.table(
        "media_resource",
        sa.column("id", sa.Integer),
        sa.column("reference_count", sa.Integer),
    )
    qm_table = sa.table(
        "question_media",
        sa.column("id", sa.Integer),
        sa.column("media_id", sa.Integer),
    )

    media_rows = connection.execute(sa.select(media_table.c.id)).all()
    for (m_id,) in media_rows:
        count = connection.execute(
            sa.select(sa.func.count(qm_table.c.id)).where(qm_table.c.media_id == m_id)
        ).scalar() or 0
        connection.execute(
            media_table.update().where(media_table.c.id == m_id).values(reference_count=count)
        )


def downgrade() -> None:
    op.drop_index("uq_question_knowledge_question_kp", table_name="question_knowledge")
