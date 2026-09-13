"""initial schema: 19 core tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-12

MVP 阶段初始化所有 19 张表的 schema。
"""
import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ===== 1. users =====
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), unique=True, index=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("real_name", sa.String(64), nullable=False),
        sa.Column("email", sa.String(128), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("role", sa.String(16), nullable=False, server_default="teacher"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("subject", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
    )

    # ===== 2. students =====
    op.create_table(
        "students",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("student_no", sa.String(64), unique=True, index=True, nullable=False),
        sa.Column("name", sa.String(64), index=True, nullable=False),
        sa.Column("gender", sa.String(8), nullable=True),
        sa.Column("grade", sa.Integer, nullable=False),
        sa.Column("enrollment_year", sa.Integer, nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("parent_phone", sa.String(20), nullable=True),
        sa.Column("total_homework_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("average_score", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("graduated_at", sa.Date, nullable=True),
    )

    # ===== 3. classes =====
    op.create_table(
        "classes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), index=True, nullable=False),
        sa.Column("grade", sa.Integer, nullable=False),
        sa.Column("semester", sa.String(16), nullable=False),
        sa.Column("head_teacher_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 4. class_students =====
    op.create_table(
        "class_students",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("class_id", sa.Integer, sa.ForeignKey("classes.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("student_id", sa.Integer, sa.ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("joined_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("left_at", sa.DateTime, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # ===== 5. knowledge_points =====
    op.create_table(
        "knowledge_points",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), unique=True, index=True, nullable=False),
        sa.Column("name", sa.String(128), index=True, nullable=False),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("knowledge_points.id"), index=True, nullable=True),
        sa.Column("grade", sa.Integer, nullable=True),
        sa.Column("semester", sa.String(16), nullable=True),
        sa.Column("chapter", sa.String(64), nullable=True),
        sa.Column("section", sa.String(64), nullable=True),
        sa.Column("difficulty_hint", sa.Integer, nullable=True),
        sa.Column("subject", sa.String(32), nullable=False, server_default="math", index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 6. sources =====
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("mime_type", sa.String(64), nullable=True),
        sa.Column("publisher", sa.String(128), nullable=True),
        sa.Column("publish_year", sa.Integer, nullable=True),
        sa.Column("grade", sa.Integer, nullable=True),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("parse_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("parse_log", sa.Text, nullable=True),
        sa.Column("parsed_at", sa.DateTime, nullable=True),
        sa.Column("total_questions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("accepted_questions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 7. questions =====
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("stem", sa.Text, nullable=False),
        sa.Column("stem_html", sa.Text, nullable=True),
        sa.Column("options", sa.JSON, nullable=True),
        sa.Column("question_type", sa.String(20), index=True, nullable=False, server_default="choice_single"),
        sa.Column("difficulty", sa.Integer, nullable=False, server_default="3"),
        sa.Column("total_score", sa.Float, nullable=False, server_default="10.0"),
        sa.Column("default_score", sa.Float, nullable=True),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("analysis", sa.Text, nullable=True),
        sa.Column("solution_steps", sa.JSON, nullable=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("source_page", sa.Integer, nullable=True),
        sa.Column("source_question_no", sa.String(32), nullable=True),
        sa.Column("checksum", sa.String(64), index=True, nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 8. sub_questions =====
    op.create_table(
        "sub_questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("question_id", sa.Integer, sa.ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("label", sa.String(16), nullable=False),
        sa.Column("stem", sa.Text, nullable=True),
        sa.Column("score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("analysis", sa.Text, nullable=True),
    )

    # ===== 9. question_answers =====
    op.create_table(
        "question_answers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("question_id", sa.Integer, sa.ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("sub_question_id", sa.Integer, sa.ForeignKey("sub_questions.id", ondelete="CASCADE"), index=True, nullable=True),
        sa.Column("blank_index", sa.Integer, nullable=False, server_default="1"),
        sa.Column("answer_text", sa.Text, nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("match_rule", sa.JSON, nullable=True),
    )

    # ===== 10. question_knowledge =====
    op.create_table(
        "question_knowledge",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("question_id", sa.Integer, sa.ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("knowledge_point_id", sa.Integer, sa.ForeignKey("knowledge_points.id"), index=True, nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 11. media_resource =====
    op.create_table(
        "media_resource",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("uuid", sa.String(36), unique=True, index=True, nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("access_url", sa.String(512), nullable=True),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("mime_type", sa.String(50), nullable=False),
        sa.Column("md5_hash", sa.String(32), index=True, nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="upload"),
        sa.Column("alt_text", sa.String(255), nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("reference_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 12. question_media =====
    op.create_table(
        "question_media",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("question_id", sa.Integer, sa.ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("media_id", sa.Integer, sa.ForeignKey("media_resource.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("usage_type", sa.String(20), nullable=False, server_default="stem"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("alt_text", sa.String(255), nullable=True),
        sa.Column("caption", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("question_id", "media_id", "usage_type", name="uq_question_media"),
    )

    # ===== 13. papers =====
    op.create_table(
        "papers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(255), index=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("total_score", sa.Float, nullable=False, server_default="100.0"),
        sa.Column("duration_minutes", sa.Integer, nullable=False, server_default="90"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("constraint_json", sa.JSON, nullable=True),
        sa.Column("grade", sa.Integer, nullable=True),
        sa.Column("semester", sa.String(16), nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("is_template", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("parent_template_id", sa.Integer, sa.ForeignKey("papers.id"), nullable=True),
        sa.Column("question_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("used_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime, nullable=True),
    )

    # ===== 14. paper_questions =====
    op.create_table(
        "paper_questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("paper_id", sa.Integer, sa.ForeignKey("papers.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("question_id", sa.Integer, sa.ForeignKey("questions.id"), index=True, nullable=False),
        sa.Column("section", sa.String(16), nullable=True),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("score", sa.Float, nullable=False, server_default="10.0"),
        sa.Column("stem_snapshot", sa.Text, nullable=False),
        sa.Column("answer_snapshot", sa.Text, nullable=True),
        sa.Column("analysis_snapshot", sa.Text, nullable=True),
        sa.Column("options_snapshot", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 15. homework =====
    op.create_table(
        "homework",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("type", sa.String(16), nullable=False, server_default="homework"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("paper_id", sa.Integer, sa.ForeignKey("papers.id"), index=True, nullable=False),
        sa.Column("class_ids", sa.JSON, nullable=True),
        sa.Column("student_ids", sa.JSON, nullable=True),
        sa.Column("assigned_at", sa.DateTime, nullable=True),
        sa.Column("due_at", sa.DateTime, nullable=True),
        sa.Column("closed_at", sa.DateTime, nullable=True),
        sa.Column("time_limit_minutes", sa.Integer, nullable=True),
        sa.Column("allow_retake", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 16. homework_results =====
    op.create_table(
        "homework_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("homework_id", sa.Integer, sa.ForeignKey("homework.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("student_id", sa.Integer, sa.ForeignKey("students.id"), index=True, nullable=False),
        sa.Column("total_score", sa.Float, nullable=True),
        sa.Column("max_score", sa.Float, nullable=False, server_default="100.0"),
        sa.Column("percentage", sa.Float, nullable=True),
        sa.Column("time_spent_minutes", sa.Integer, nullable=True),
        sa.Column("result_detail", sa.JSON, nullable=True),
        sa.Column("teacher_comment", sa.Text, nullable=True),
        sa.Column("input_source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("recorded_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("recorded_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 17. student_kp_stats =====
    op.create_table(
        "student_kp_stats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("student_id", sa.Integer, sa.ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("knowledge_point_id", sa.Integer, sa.ForeignKey("knowledge_points.id"), index=True, nullable=False),
        sa.Column("total_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("accuracy", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("weighted_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("recent_5_accuracy", sa.Float, nullable=True),
        sa.Column("trend", sa.String(16), nullable=True),
        sa.Column("last_practiced_at", sa.DateTime, nullable=True),
        sa.Column("last_updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 18. weak_points =====
    op.create_table(
        "weak_points",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("student_id", sa.Integer, sa.ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("knowledge_point_id", sa.Integer, sa.ForeignKey("knowledge_points.id"), index=True, nullable=False),
        sa.Column("accuracy", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("recommended_practice_count", sa.Integer, nullable=False, server_default="5"),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("detected_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ===== 19. audit_log =====
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), index=True, nullable=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("action", sa.String(32), index=True, nullable=False),
        sa.Column("resource_type", sa.String(32), index=True, nullable=False),
        sa.Column("resource_id", sa.Integer, index=True, nullable=True),
        sa.Column("changes", sa.JSON, nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    # 反向删除（按依赖关系倒序）
    op.drop_table("audit_log")
    op.drop_table("weak_points")
    op.drop_table("student_kp_stats")
    op.drop_table("homework_results")
    op.drop_table("homework")
    op.drop_table("paper_questions")
    op.drop_table("papers")
    op.drop_table("question_media")
    op.drop_table("media_resource")
    op.drop_table("question_knowledge")
    op.drop_table("question_answers")
    op.drop_table("sub_questions")
    op.drop_table("questions")
    op.drop_table("sources")
    op.drop_table("knowledge_points")
    op.drop_table("class_students")
    op.drop_table("classes")
    op.drop_table("students")
    op.drop_table("users")
