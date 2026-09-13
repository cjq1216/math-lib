"""题目 API schema。"""

from datetime import datetime

from pydantic import Field

from app.models.question import QuestionType
from app.schemas.common import StrictSchema


class QuestionCreate(StrictSchema):
    stem: str = Field(min_length=1)
    stem_html: str | None = None
    question_type: QuestionType = QuestionType.CHOICE_SINGLE
    difficulty: int = Field(default=3, ge=1, le=5)
    total_score: float = Field(default=10.0, ge=0)
    default_score: float | None = Field(default=None, ge=0)
    options: list[str] | None = None
    answer: str | None = None
    analysis: str | None = None
    solution_steps: list[dict] | None = None
    source_id: int | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_question_no: str | None = Field(default=None, max_length=32)
    tags: list[str] | None = None
    is_verified: bool = False


class QuestionUpdate(StrictSchema):
    stem: str | None = Field(default=None, min_length=1)
    stem_html: str | None = None
    question_type: QuestionType | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    total_score: float | None = Field(default=None, ge=0)
    default_score: float | None = Field(default=None, ge=0)
    options: list[str] | None = None
    answer: str | None = None
    analysis: str | None = None
    solution_steps: list[dict] | None = None
    source_id: int | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_question_no: str | None = Field(default=None, max_length=32)
    tags: list[str] | None = None
    is_verified: bool | None = None


class QuestionListItem(StrictSchema):
    id: int
    stem: str
    question_type: QuestionType
    difficulty: int
    total_score: float
    options: list[str] | None = None
    answer: str | None = None
    analysis: str | None = None
    tags: list[str] | None = None
    is_verified: bool
    created_at: datetime


class SubQuestionInput(StrictSchema):
    label: str | None = Field(default=None, max_length=16)
    stem: str | None = None
    score: float = Field(default=0, ge=0)
    answer: str | None = None
    analysis: str | None = None


class SubQuestionRead(StrictSchema):
    id: int
    label: str
    stem: str | None = None
    score: float
    answer: str | None = None


class QuestionAnswerRead(StrictSchema):
    id: int
    blank_index: int
    answer_text: str
    is_primary: bool


class QuestionKnowledgeInput(StrictSchema):
    kp_id: int = Field(gt=0)
    is_primary: bool = False
    weight: float = Field(default=1.0, ge=0, le=1)


class QuestionKnowledgeRead(StrictSchema):
    kp_id: int
    is_primary: bool


class QuestionKnowledgeSet(StrictSchema):
    items: list[QuestionKnowledgeInput] = Field(default_factory=list)


class SubQuestionSet(StrictSchema):
    items: list[SubQuestionInput] = Field(default_factory=list)


class QuestionRead(QuestionListItem):
    sub_questions: list[SubQuestionRead] = Field(default_factory=list)
    answers: list[QuestionAnswerRead] = Field(default_factory=list)
    knowledge_points: list[QuestionKnowledgeRead] = Field(default_factory=list)


class QuestionListResponse(StrictSchema):
    total: int = Field(ge=0)
    items: list[QuestionListItem]


class ReplaceResponse(StrictSchema):
    ok: bool = True
    count: int = Field(ge=0)
