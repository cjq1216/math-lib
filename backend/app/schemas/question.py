"""题目 API schema。"""

from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.media import MediaUsageType
from app.models.question import QuestionType
from app.schemas.common import StrictSchema


class SubQuestionInput(StrictSchema):
    label: str | None = Field(default=None, max_length=16)
    stem: str | None = None
    score: float = Field(default=0.0, ge=0)
    answer: str | None = None
    analysis: str | None = None
    display_order: int = Field(default=0, ge=0)


class SubQuestionRead(StrictSchema):
    id: int
    label: str
    stem: str | None = None
    score: float
    answer: str | None = None
    analysis: str | None = None
    display_order: int = 0


class QuestionAnswerInput(StrictSchema):
    blank_index: int = Field(default=1, ge=1)
    answer_text: str = Field(min_length=1)
    is_primary: bool = True
    match_rule: dict[str, Any] | None = None


class QuestionAnswerRead(StrictSchema):
    id: int
    blank_index: int
    answer_text: str
    is_primary: bool
    match_rule: dict[str, Any] | None = None


class QuestionKnowledgeInput(StrictSchema):
    kp_id: int = Field(gt=0)
    is_primary: bool = False
    weight: float = Field(default=1.0, ge=0, le=1)


class QuestionKnowledgeRead(StrictSchema):
    kp_id: int
    is_primary: bool
    weight: float = 1.0


class QuestionMediaInput(StrictSchema):
    media_id: int = Field(gt=0)
    usage_type: MediaUsageType = MediaUsageType.STEM
    display_order: int = Field(default=0, ge=0)
    alt_text: str | None = Field(default=None, max_length=255)
    caption: str | None = Field(default=None, max_length=64)


class QuestionMediaRead(StrictSchema):
    id: int
    media_id: int
    usage_type: MediaUsageType
    display_order: int
    alt_text: str | None = None
    caption: str | None = None
    access_url: str | None = None
    original_name: str | None = None


class QuestionCreate(StrictSchema):
    stem: str = Field(min_length=1)
    options: list[str] | None = None
    question_type: QuestionType = QuestionType.CHOICE_SINGLE
    difficulty: int = Field(default=3, ge=1, le=5)
    total_score: float = Field(default=10.0, ge=0)
    default_score: float | None = Field(default=None, ge=0)
    answer: str | None = None
    analysis: str | None = None
    tags: list[str] | None = None
    is_verified: bool = False
    source_id: int | None = None
    source_page: int | None = None
    source_question_no: str | None = Field(default=None, max_length=32)

    # 聚合创建子实体
    sub_questions: list[SubQuestionInput] | None = None
    answers: list[QuestionAnswerInput] | None = None
    knowledge_points: list[QuestionKnowledgeInput] | None = None
    media_items: list[QuestionMediaInput] | None = None


class QuestionUpdate(StrictSchema):
    stem: str | None = Field(default=None, min_length=1)
    options: list[str] | None = None
    question_type: QuestionType | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    total_score: float | None = Field(default=None, ge=0)
    default_score: float | None = Field(default=None, ge=0)
    answer: str | None = None
    analysis: str | None = None
    tags: list[str] | None = None
    is_verified: bool | None = None
    source_id: int | None = None
    source_page: int | None = None
    source_question_no: str | None = Field(default=None, max_length=32)

    # 聚合更新子实体（传入时全量更新，不传保持原样）
    sub_questions: list[SubQuestionInput] | None = None
    answers: list[QuestionAnswerInput] | None = None
    knowledge_points: list[QuestionKnowledgeInput] | None = None
    media_items: list[QuestionMediaInput] | None = None


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
    checksum: str | None = None
    created_at: datetime


class QuestionRead(QuestionListItem):
    sub_questions: list[SubQuestionRead] = Field(default_factory=list)
    answers: list[QuestionAnswerRead] = Field(default_factory=list)
    knowledge_points: list[QuestionKnowledgeRead] = Field(default_factory=list)
    media_items: list[QuestionMediaRead] = Field(default_factory=list)


class QuestionKnowledgeSet(StrictSchema):
    items: list[QuestionKnowledgeInput] = Field(default_factory=list)


class SubQuestionSet(StrictSchema):
    items: list[SubQuestionInput] = Field(default_factory=list)


class QuestionListResponse(StrictSchema):
    total: int = Field(ge=0)
    items: list[QuestionListItem]


class ReplaceResponse(StrictSchema):
    ok: bool = True
    count: int = Field(ge=0)
