"""add homework roster snapshots and question results

Revision ID: 0005_homework_roster_and_question_results
Revises: 0004_auth_and_class_access
Create Date: 2026-10-01
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "0005_homework_roster_and_question_results"
down_revision = "0004_auth_and_class_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 创建 homework_classes 表
    op.create_table(
        "homework_classes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("homework_id", sa.Integer, sa.ForeignKey("homework.id", ondelete="CASCADE"), nullable=False),
        sa.Column("class_id", sa.Integer, sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("homework_id", "class_id", name="uq_homework_classes_homework_class"),
    )
    op.create_index("ix_homework_classes_homework_id", "homework_classes", ["homework_id"])
    op.create_index("ix_homework_classes_class_id", "homework_classes", ["class_id"])

    # 2. 创建 homework_students 表（名单快照）
    op.create_table(
        "homework_students",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("homework_id", sa.Integer, sa.ForeignKey("homework.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("class_id", sa.Integer, sa.ForeignKey("classes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("homework_id", "student_id", name="uq_homework_students_homework_student"),
    )
    op.create_index("ix_homework_students_homework_id", "homework_students", ["homework_id"])
    op.create_index("ix_homework_students_student_id", "homework_students", ["student_id"])
    op.create_index("ix_homework_students_class_id", "homework_students", ["class_id"])

    # 3. 创建 homework_question_results 表（每题明细）
    op.create_table(
        "homework_question_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("homework_result_id", sa.Integer, sa.ForeignKey("homework_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paper_question_id", sa.Integer, sa.ForeignKey("paper_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer, sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Float, nullable=False, server_default="0"),
        sa.Column("max_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("is_correct", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("answer_text", sa.Text, nullable=True),
        sa.Column("time_spent_seconds", sa.Integer, nullable=True),
        sa.Column("recorded_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("homework_result_id", "paper_question_id", name="uq_hw_q_results_hw_res_paper_q"),
    )
    op.create_index("ix_homework_question_results_homework_result_id", "homework_question_results", ["homework_result_id"])
    op.create_index("ix_homework_question_results_paper_question_id", "homework_question_results", ["paper_question_id"])
    op.create_index("ix_homework_question_results_question_id", "homework_question_results", ["question_id"])

    # 4. 创建唯一索引
    op.create_index("uq_homework_results_homework_student", "homework_results", ["homework_id", "student_id"], unique=True)
    op.create_index("uq_student_kp_stats_student_kp", "student_kp_stats", ["student_id", "knowledge_point_id"], unique=True)
    op.create_index("uq_weak_points_student_kp", "weak_points", ["student_id", "knowledge_point_id"], unique=True)

    # 5. 回填历史数据
    connection = op.get_bind()

    # 回填 homework_classes 与 homework_students
    homework_table = sa.table(
        "homework",
        sa.column("id", sa.Integer),
        sa.column("class_ids", sa.JSON),
        sa.column("student_ids", sa.JSON),
    )
    class_students_table = sa.table(
        "class_students",
        sa.column("class_id", sa.Integer),
        sa.column("student_id", sa.Integer),
        sa.column("left_at", sa.DateTime),
    )
    homework_classes_table = sa.table(
        "homework_classes",
        sa.column("homework_id", sa.Integer),
        sa.column("class_id", sa.Integer),
    )
    homework_students_table = sa.table(
        "homework_students",
        sa.column("homework_id", sa.Integer),
        sa.column("student_id", sa.Integer),
        sa.column("class_id", sa.Integer),
    )

    rows = connection.execute(sa.select(homework_table.c.id, homework_table.c.class_ids, homework_table.c.student_ids)).all()
    hw_class_records = []
    hw_student_records = []

    for hw_id, raw_cids, raw_sids in rows:
        cids = raw_cids if isinstance(raw_cids, list) else (json.loads(raw_cids) if isinstance(raw_cids, str) else [])
        sids = raw_sids if isinstance(raw_sids, list) else (json.loads(raw_sids) if isinstance(raw_sids, str) else [])

        seen_classes = set()
        for cid in cids:
            if isinstance(cid, int) and cid not in seen_classes:
                seen_classes.add(cid)
                hw_class_records.append({"homework_id": hw_id, "class_id": cid})

        seen_students = set()
        # 先加入所选班级中未离班学生
        if seen_classes:
            st_rows = connection.execute(
                sa.select(class_students_table.c.class_id, class_students_table.c.student_id).where(
                    class_students_table.c.class_id.in_(list(seen_classes)),
                    class_students_table.c.left_at.is_(None),
                )
            ).all()
            for c_id, s_id in st_rows:
                if s_id not in seen_students:
                    seen_students.add(s_id)
                    hw_student_records.append({
                        "homework_id": hw_id,
                        "student_id": s_id,
                        "class_id": c_id,
                    })

        # 再加入指定学生名单（若尚未加入）
        for sid in sids:
            if isinstance(sid, int) and sid not in seen_students:
                seen_students.add(sid)
                hw_student_records.append({
                    "homework_id": hw_id,
                    "student_id": sid,
                    "class_id": None,
                })

    if hw_class_records:
        connection.execute(homework_classes_table.insert(), hw_class_records)
    if hw_student_records:
        connection.execute(homework_students_table.insert(), hw_student_records)


def downgrade() -> None:
    op.drop_index("uq_weak_points_student_kp", table_name="weak_points")
    op.drop_index("uq_student_kp_stats_student_kp", table_name="student_kp_stats")
    op.drop_index("uq_homework_results_homework_student", table_name="homework_results")

    op.drop_index("ix_homework_question_results_question_id", table_name="homework_question_results")
    op.drop_index("ix_homework_question_results_paper_question_id", table_name="homework_question_results")
    op.drop_index("ix_homework_question_results_homework_result_id", table_name="homework_question_results")
    op.drop_table("homework_question_results")

    op.drop_index("ix_homework_students_class_id", table_name="homework_students")
    op.drop_index("ix_homework_students_student_id", table_name="homework_students")
    op.drop_index("ix_homework_students_homework_id", table_name="homework_students")
    op.drop_table("homework_students")

    op.drop_index("ix_homework_classes_class_id", table_name="homework_classes")
    op.drop_index("ix_homework_classes_homework_id", table_name="homework_classes")
    op.drop_table("homework_classes")
