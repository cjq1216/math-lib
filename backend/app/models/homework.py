"""
作业/试卷下发 + 学生作答结果
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import JSON, Field, SQLModel

from app.core.datetime_utils import utc_now


class HomeworkType(str, Enum):
    """作业类型"""

    HOMEWORK = "homework"   # 作业（不限时）
    QUIZ = "quiz"           # 测验（限时）


class HomeworkStatus(str, Enum):
    """作业状态"""

    DRAFT = "draft"
    ASSIGNED = "assigned"   # 已下发
    CLOSED = "closed"       # 已截止
    GRADED = "graded"       # 已批改


class Homework(SQLModel, table=True):
    """
    作业/试卷下发

    基于 paper 创建，可关联到班级
    """

    __tablename__ = "homework"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(max_length=255)
    type: HomeworkType = Field(default=HomeworkType.HOMEWORK)
    status: HomeworkStatus = Field(default=HomeworkStatus.DRAFT)

    # 来源试卷
    paper_id: int = Field(foreign_key="papers.id", index=True)

    # 关联班级（多个）
    class_ids: Optional[list[int]] = Field(default=None, sa_type=JSON)

    # 关联学生（具体名单，覆盖班级默认）
    student_ids: Optional[list[int]] = Field(default=None, sa_type=JSON)

    # 时间
    assigned_at: Optional[datetime] = Field(default=None)
    due_at: Optional[datetime] = Field(default=None)
    closed_at: Optional[datetime] = Field(default=None)

    # 限制
    time_limit_minutes: Optional[int] = Field(default=None, description="限时（分钟）")
    allow_retake: bool = Field(default=False)

    notes: Optional[str] = Field(default=None)
    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HomeworkClass(SQLModel, table=True):
    """作业下发关联班级"""

    __tablename__ = "homework_classes"
    __table_args__ = (
        UniqueConstraint("homework_id", "class_id", name="uq_homework_classes_homework_class"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    homework_id: int = Field(foreign_key="homework.id", index=True, ondelete="CASCADE")
    class_id: int = Field(foreign_key="classes.id", index=True, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=utc_now)


class HomeworkStudent(SQLModel, table=True):
    """作业下发学生名单快照（隔离后续学生转班影响）"""

    __tablename__ = "homework_students"
    __table_args__ = (
        UniqueConstraint("homework_id", "student_id", name="uq_homework_students_homework_student"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    homework_id: int = Field(foreign_key="homework.id", index=True, ondelete="CASCADE")
    student_id: int = Field(foreign_key="students.id", index=True, ondelete="CASCADE")
    class_id: Optional[int] = Field(default=None, foreign_key="classes.id", ondelete="SET NULL")
    created_at: datetime = Field(default_factory=utc_now)


class HomeworkResult(SQLModel, table=True):
    """
    学生作答结果

    每条记录对应 (作业, 学生)，存储总分和各题得分。
    详细到每题的得分存在 result_detail JSON 字段。
    """

    __tablename__ = "homework_results"
    __table_args__ = (
        UniqueConstraint("homework_id", "student_id", name="uq_homework_results_homework_student"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    homework_id: int = Field(foreign_key="homework.id", index=True, ondelete="CASCADE")
    student_id: int = Field(foreign_key="students.id", index=True)

    # 总分
    total_score: Optional[float] = Field(default=None)
    max_score: float = Field(default=100.0)
    percentage: Optional[float] = Field(default=None, description="百分比")

    # 用时
    time_spent_minutes: Optional[int] = Field(default=None)

    # 各题详细得分
    # 格式：[{"question_id": 1, "score": 5, "is_correct": true, "kp_ids": [1, 2]}, ...]
    result_detail: Optional[list[dict]] = Field(default=None, sa_type=JSON)

    # 教师评语
    teacher_comment: Optional[str] = Field(default=None)

    # 来源：手工录入 / Excel 导入
    input_source: str = Field(default="manual", max_length=32)

    recorded_by: Optional[int] = Field(default=None, foreign_key="users.id")
    recorded_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HomeworkQuestionResult(SQLModel, table=True):
    """
    单题成绩明细

    记录学生某次作业中每道试卷题目的得分、满分、对错状态与作答文本。
    用于精确计算知识点掌握度与薄弱点。
    """

    __tablename__ = "homework_question_results"
    __table_args__ = (
        UniqueConstraint("homework_result_id", "paper_question_id", name="uq_hw_q_results_hw_res_paper_q"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    homework_result_id: int = Field(foreign_key="homework_results.id", index=True, ondelete="CASCADE")
    paper_question_id: int = Field(foreign_key="paper_questions.id", index=True, ondelete="CASCADE")
    question_id: int = Field(foreign_key="questions.id", index=True, ondelete="CASCADE")

    score: float = Field(default=0.0)
    max_score: float = Field(default=0.0)
    is_correct: bool = Field(default=False)

    answer_text: Optional[str] = Field(default=None)
    time_spent_seconds: Optional[int] = Field(default=None)
    recorded_at: datetime = Field(default_factory=utc_now)
