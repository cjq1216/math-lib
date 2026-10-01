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




class HomeworkStudentRead(StrictSchema):
    student_id: int
    student_no: str | None = None
    name: str
    class_id: int | None = None
    class_name: str | None = None


class HomeworkPaperQuestionRead(StrictSchema):
    id: int
    question_id: int
    display_order: int
    score: float
    stem_snapshot: str | None = None
    question_type: str | None = None


class QuestionResultInput(StrictSchema):
    paper_question_id: int
    score: float = Field(ge=0)
    is_correct: bool | None = None
    answer_text: str | None = None
    time_spent_seconds: int | None = Field(default=None, ge=0)


class QuestionResultRead(StrictSchema):
    id: int
    paper_question_id: int
    question_id: int
    score: float
    max_score: float
    is_correct: bool
    answer_text: str | None = None
    time_spent_seconds: int | None = None
class HomeworkResultCreate(StrictSchema):
    student_id: int
    total_score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, gt=0)
    time_spent_minutes: int | None = Field(default=None, ge=0)
    result_detail: list[dict] | None = None
    question_results: list[QuestionResultInput] | None = None
    teacher_comment: str | None = None


class HomeworkResultRead(StrictSchema):
    id: int
    student_id: int
    total_score: float | None = None
    max_score: float
    percentage: float | None = None
    time_spent_minutes: int | None = None
    question_results: list[QuestionResultRead] = Field(default_factory=list)


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
    target_students: list[HomeworkStudentRead] = Field(default_factory=list)
    paper_questions: list[HomeworkPaperQuestionRead] = Field(default_factory=list)
