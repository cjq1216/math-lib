"""知识点 API schema。"""

from pydantic import Field, model_validator

from app.schemas.common import StrictSchema


class KnowledgePointCreate(StrictSchema):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    parent_id: int | None = None
    grade: int | None = Field(default=None, ge=7, le=9)
    semester: str | None = Field(default=None, max_length=16)
    chapter: str | None = Field(default=None, max_length=64)
    section: str | None = Field(default=None, max_length=64)
    difficulty_hint: int | None = Field(default=None, ge=1, le=5)
    subject: str = Field(default="math", max_length=32)
    description: str | None = None
    display_order: int = 0


class KnowledgePointUpdate(StrictSchema):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: int | None = None
    grade: int | None = Field(default=None, ge=7, le=9)
    semester: str | None = Field(default=None, max_length=16)
    chapter: str | None = Field(default=None, max_length=64)
    section: str | None = Field(default=None, max_length=64)
    difficulty_hint: int | None = Field(default=None, ge=1, le=5)
    subject: str | None = Field(default=None, max_length=32)
    description: str | None = None
    display_order: int | None = None


class KnowledgePointRead(StrictSchema):
    id: int
    code: str
    name: str
    parent_id: int | None = None
    grade: int | None = None
    semester: str | None = None
    chapter: str | None = None
    section: str | None = None
    difficulty_hint: int | None = None
    subject: str = "math"
    description: str | None = None
    children: list["KnowledgePointRead"] | None = None


class KnowledgeImportRequest(StrictSchema):
    items: list[KnowledgePointCreate]


class TargetedPracticeRequest(StrictSchema):
    count: int = Field(default=5, ge=1, le=100)
    difficulty_min: int = Field(default=1, ge=1, le=5)
    difficulty_max: int = Field(default=5, ge=1, le=5)

    @model_validator(mode="after")
    def validate_range(self):
        if self.difficulty_min > self.difficulty_max:
            raise ValueError("difficulty_min 不能大于 difficulty_max")
        return self
