"""
作业/试卷下发 + 学生作答结果
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import JSON, Field, SQLModel


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
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HomeworkResult(SQLModel, table=True):
    """
    学生作答结果

    每条记录对应 (作业, 学生)，存储总分和各题得分。
    详细到每题的得分存在 result_detail JSON 字段。
    """

    __tablename__ = "homework_results"

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
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
