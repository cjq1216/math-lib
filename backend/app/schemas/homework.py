"""作业与成绩 API schema。"""

from datetime import datetime

from pydantic import Field

from app.models.homework import HomeworkStatus, HomeworkType
from app.schemas.common import StrictSchema


class HomeworkCreate(StrictSchema):
    title: str = Field(min_length=1, max_length=255)
    type: HomeworkType = HomeworkType.HOMEWORK
    paper_id: int
    class_ids: list[int] = Field(default_factory=list)
    student_ids: list[int] = Field(default_factory=list)
    due_at: datetime | None = None
    time_limit_minutes: int | None = Field(default=None, ge=1)
    allow_retake: bool = False
    notes: str | None = None


class HomeworkSummary(StrictSchema):
    id: int
    title: str
    type: HomeworkType
    status: HomeworkStatus
    paper_id: int
    due_at: datetime | None = None
    created_at: datetime


class HomeworkResultCreate(StrictSchema):
    student_id: int
    total_score: float = Field(default=0, ge=0)
    max_score: float = Field(default=100, gt=0)
    time_spent_minutes: int | None = Field(default=None, ge=0)
    result_detail: list[dict] | None = None
    teacher_comment: str | None = None


class HomeworkResultRead(StrictSchema):
    id: int
    student_id: int
    total_score: float | None = None
    max_score: float
    percentage: float | None = None
    time_spent_minutes: int | None = None


class HomeworkRead(StrictSchema):
    id: int
    title: str
    type: HomeworkType
    status: HomeworkStatus
    paper_id: int
    class_ids: list[int] | None = None
    student_ids: list[int] | None = None
    due_at: datetime | None = None
    results: list[HomeworkResultRead] = Field(default_factory=list)
