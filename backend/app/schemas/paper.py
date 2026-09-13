"""试卷与智能组卷 API schema。"""

from datetime import datetime

from pydantic import Field, model_validator

from app.models.paper import PaperStatus
from app.schemas.common import StrictSchema


class PaperConstraint(StrictSchema):
    total_score: float = Field(default=100, gt=0)
    duration_minutes: int = Field(default=90, ge=1)
    type_distribution: dict[str, int] = Field(default_factory=dict)
    difficulty_ratio: dict[str, float] = Field(default_factory=dict)
    required_kps: list[int] = Field(default_factory=list)
    forbidden_kps: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_knowledge_sets(self):
        overlap = set(self.required_kps) & set(self.forbidden_kps)
        if overlap:
            raise ValueError("必含知识点和禁含知识点不能重叠")
        if any(count < 0 for count in self.type_distribution.values()):
            raise ValueError("题型数量不能为负数")
        if any(ratio < 0 for ratio in self.difficulty_ratio.values()):
            raise ValueError("难度比例不能为负数")
        return self


class PaperCreate(StrictSchema):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    total_score: float = Field(default=100, gt=0)
    duration_minutes: int = Field(default=90, ge=1)
    grade: int | None = Field(default=None, ge=7, le=9)
    semester: str | None = Field(default=None, max_length=16)
    tags: list[str] | None = None
    constraint: dict | None = None


class PaperGenerateRequest(StrictSchema):
    title: str = Field(default="智能组卷", min_length=1, max_length=255)
    constraint: PaperConstraint


class PaperSummary(StrictSchema):
    id: int
    title: str
    total_score: float
    duration_minutes: int
    status: PaperStatus
    question_count: int
    created_at: datetime


class PaperQuestionRead(StrictSchema):
    id: int
    display_order: int
    section: str | None = None
    score: float
    stem: str
    answer: str | None = None
    analysis: str | None = None
    options: list[str] | None = None


class PaperRead(StrictSchema):
    id: int
    title: str
    description: str | None = None
    total_score: float
    duration_minutes: int
    status: PaperStatus
    questions: list[PaperQuestionRead]


class PaperGenerateQuestion(StrictSchema):
    id: int
    display_order: int
    section: str | None = None
    score: float
    stem: str


class PaperGenerateResponse(StrictSchema):
    paper_id: int
    question_count: int
    total_score: float
    questions: list[PaperGenerateQuestion]


class ExportRequest(StrictSchema):
    format: str = Field(default="word", pattern="^(word|markdown|pdf)$")
