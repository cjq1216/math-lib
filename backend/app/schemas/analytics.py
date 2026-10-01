"""学情分析 API schema。"""

from datetime import datetime

from pydantic import Field, model_validator

from app.models.question import QuestionType
from app.schemas.common import StrictSchema


class TargetedPracticeRequest(StrictSchema):
    count: int = Field(default=5, ge=1, le=100)
    difficulty_min: int = Field(default=1, ge=1, le=5)
    difficulty_max: int = Field(default=5, ge=1, le=5)

    @model_validator(mode="after")
    def validate_range(self):
        if self.difficulty_min > self.difficulty_max:
            raise ValueError("difficulty_min 不能大于 difficulty_max")
        return self


class WeakPointSummary(StrictSchema):
    kp_id: int
    accuracy: float
    severity: str
    trend: str | None = None
    recent_5_accuracy: float | None = None

class StudentOverview(StrictSchema):
    student_id: int
    name: str
    average_score: float | None = None
    total_homework: int
    knowledge_points_practiced: int
    weak_points: list[WeakPointSummary]


class WeakPointRead(WeakPointSummary):
    kp_name: str | None = None
    kp_code: str | None = None
    attempts: int
    recommended_practice_count: int
    is_resolved: bool = False
    resolved_at: datetime | None = None

class PracticeQuestion(StrictSchema):
    id: int
    stem: str
    question_type: QuestionType
    difficulty: int


class TargetedPracticeResponse(StrictSchema):
    questions: list[PracticeQuestion]
    based_on: list[int] = Field(default_factory=list)
    total: int = 0
    message: str | None = None


class RankRow(StrictSchema):
    rank: int
    student_id: int
    name: str
    student_no: str
    total_score: float | None = None
    max_score: float
    percentage: float | None = None


class ClassOverview(StrictSchema):
    class_id: int
    student_count: int
    total_homework: int
    avg_score: float | None = None
    max_score: float | None = None
    min_score: float | None = None


class CreateTargetedHomeworkRequest(StrictSchema):
    title: str = Field(min_length=1, max_length=255)
    question_ids: list[int] = Field(min_length=1)
    score_per_question: float = Field(default=5.0, gt=0)


class CreateTargetedHomeworkResponse(StrictSchema):
    homework_id: int
    paper_id: int
    title: str
